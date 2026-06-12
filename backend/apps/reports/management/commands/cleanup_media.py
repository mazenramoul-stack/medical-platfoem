"""Management command to clean up old files under MEDIA_ROOT.

Usage:
    python manage.py cleanup_media --days N [--delete] [--include-reports]

Dry-run by default: lists files under the MEDIA_ROOT subdirectories whose
mtime is older than N days, plus the total size that would be freed.
Nothing is removed unless --delete is passed.

The ``reports/`` subdirectory is skipped by default because generated PDF
reports deliberately survive patient deletion (see CLAUDE.md); pass
--include-reports to opt in.

Safety properties:
    * Never follows symlinks (symlinked directories are pruned, symlinked
      files are skipped). Windows junctions are pruned too (os.path.islink
      misses them on Python 3.10, so directories are also realpath-checked).
    * Never touches anything outside MEDIA_ROOT; every candidate file's
      realpath must resolve inside it, and a file resolving under reports/
      counts as a report even when reached through a junction.
    * No database access at all, so it works even when MongoDB is down.
"""

import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

REPORTS_DIRNAME = 'reports'


def _human_size(num_bytes):
    """Format a byte count as a human-readable string.

    Args:
        num_bytes: Size in bytes.

    Returns:
        str: e.g. ``"1.2 MB"``.
    """
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024.0 or unit == 'GB':
            return '%.1f %s' % (size, unit)
        size /= 1024.0
    return '%.1f GB' % size  # pragma: no cover - unreachable


class Command(BaseCommand):
    """Delete (or list) media files older than a given number of days."""

    help = (
        'List or delete files under MEDIA_ROOT older than N days (mtime). '
        'Dry-run by default; pass --delete to actually remove files. '
        "The 'reports/' subdir is skipped unless --include-reports is given. "
        'Performs no database access.'
    )

    # Skip system checks: this command must run even when MongoDB is down.
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            required=True,
            help='Age threshold in days; files with mtime older than this '
                 'are matched. Use 0 to match everything.',
        )
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete the matched files (default is dry-run).',
        )
        parser.add_argument(
            '--include-reports',
            action='store_true',
            help="Also clean the 'reports/' subdir (skipped by default: "
                 'generated PDFs survive patient deletion by design).',
        )

    def handle(self, *args, **options):
        days = options['days']
        do_delete = options['delete']
        include_reports = options['include_reports']

        if days < 0:
            raise CommandError('--days must be >= 0.')

        media_root = os.path.realpath(str(settings.MEDIA_ROOT))
        if not os.path.isdir(media_root):
            self.stdout.write(self.style.WARNING(
                'MEDIA_ROOT does not exist (%s) - nothing to do.' % media_root
            ))
            return

        cutoff = time.time() - days * 86400

        self.stdout.write('Media cleanup under: %s' % media_root)
        if do_delete:
            self.stdout.write(self.style.WARNING('Mode: DELETE'))
        else:
            self.stdout.write(
                'Mode: DRY RUN (no files will be removed; pass --delete '
                'to remove them)'
            )
        if not include_reports:
            self.stdout.write(
                "Skipping '%s/' (pass --include-reports to include it)"
                % REPORTS_DIRNAME
            )

        matched = 0
        total_bytes = 0
        deleted = 0
        freed_bytes = 0
        failures = 0

        for path, size in self._iter_old_files(
                media_root, cutoff, include_reports):
            matched += 1
            total_bytes += size
            rel = os.path.relpath(path, media_root)
            self.stdout.write('  %s  (%s)' % (rel, _human_size(size)))
            if do_delete:
                try:
                    os.remove(path)
                except OSError as exc:
                    failures += 1
                    self.stderr.write(self.style.ERROR(
                        '  FAILED to delete %s: %s' % (rel, exc)
                    ))
                else:
                    deleted += 1
                    freed_bytes += size

        if do_delete:
            summary = 'Deleted %d file(s), freed %s.' % (
                deleted, _human_size(freed_bytes))
            if failures:
                summary += ' %d deletion(s) failed.' % failures
                self.stdout.write(self.style.ERROR(summary))
            else:
                self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Matched %d file(s), %s would be freed. '
                'Re-run with --delete to remove them.'
                % (matched, _human_size(total_bytes))
            ))

    def _iter_old_files(self, media_root, cutoff, include_reports):
        """Yield ``(path, size)`` for regular files older than the cutoff.

        Walks only the immediate subdirectories of ``media_root`` (mri, ecg,
        echo, eeg, reports, ...). Symlinks are never followed: symlinked
        directories are pruned from the walk and symlinked files are skipped.
        Any path that does not resolve inside ``media_root`` is ignored.

        Args:
            media_root: Real (resolved) absolute path of MEDIA_ROOT.
            cutoff: Unix timestamp; files with mtime < cutoff are yielded.
            include_reports: Whether to descend into the reports/ subdir.

        Yields:
            tuple: ``(absolute_path, size_in_bytes)``.
        """
        try:
            entries = sorted(os.listdir(media_root))
        except OSError as exc:
            self.stderr.write(self.style.ERROR(
                'Cannot list MEDIA_ROOT: %s' % exc))
            return

        for entry in entries:
            top = os.path.join(media_root, entry)
            if not os.path.isdir(top) or os.path.islink(top):
                continue
            if entry == REPORTS_DIRNAME and not include_reports:
                continue

            reports_root = os.path.normcase(
                os.path.join(media_root, REPORTS_DIRNAME))

            for dirpath, dirnames, filenames in os.walk(
                    top, followlinks=False):
                # Prune symlinked directories so we never walk through them.
                # os.path.islink() returns False for Windows junctions on
                # Python 3.10, so also require realpath == the path itself.
                dirnames[:] = [
                    d for d in sorted(dirnames)
                    if not os.path.islink(os.path.join(dirpath, d))
                    and os.path.normcase(
                        os.path.realpath(os.path.join(dirpath, d)))
                    == os.path.normcase(os.path.join(dirpath, d))
                ]
                for name in sorted(filenames):
                    fpath = os.path.join(dirpath, name)
                    if os.path.islink(fpath):
                        continue
                    # Belt-and-braces: never act outside MEDIA_ROOT. A
                    # junction to another drive makes commonpath raise
                    # ValueError - treat that as outside.
                    real = os.path.normcase(os.path.realpath(fpath))
                    root = os.path.normcase(media_root)
                    try:
                        if os.path.commonpath([root, real]) != root:
                            continue
                        # A file whose real location is under reports/ is a
                        # report, even if reached through a junction.
                        if (not include_reports and
                                os.path.commonpath([reports_root, real])
                                == reports_root):
                            continue
                    except ValueError:
                        continue
                    try:
                        stat = os.stat(fpath, follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.st_mtime < cutoff:
                        yield fpath, stat.st_size
