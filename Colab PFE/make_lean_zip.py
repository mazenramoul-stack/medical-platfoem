"""Build a lean medical-platform.zip for the Colab GPU jobs.

The Colab notebooks in this folder expect a zip of the repo at the root of
your Google Drive (``My Drive/medical-platform.zip``) — the same pattern as
tools/COLAB.md. A naive zip of the project is ~2.5 GB; this script excludes
everything the GPU jobs never read (venv, node_modules, datasets, media,
screenshots) and produces a zip of roughly 30-60 MB that still contains all
code plus the bundled BIOT encoder checkpoint.

Usage (from the project root, any Python 3.10+, no extra packages):

    python "Colab PFE/make_lean_zip.py"

Output: medical-platform.zip in the parent directory (e:\\MASTER), ready to
upload to the root of Google Drive.
"""

import os
import zipfile

# Directory names pruned wherever they appear.
EXCLUDE_DIRS = {
    'venv', 'node_modules', '__pycache__', '.git', 'dist',
    'data', 'media', 'samples', 'SCREENSHOTS', '.pytest_cache',
    # EchoNet checkpoints are ~540 MB and no Colab job here needs them
    # (the echo eval has its own flow in tools/COLAB.md).
    'echonet',
}
# File extensions never needed on Colab.
EXCLUDE_EXTS = {'.pyc', '.pyo', '.zip', '.mp4', '.avi'}


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(os.path.dirname(repo_root), 'medical-platform.zip')

    n_files = 0
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [d for d in sorted(dirnames) if d not in EXCLUDE_DIRS]
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower() in EXCLUDE_EXTS:
                    continue
                fpath = os.path.join(dirpath, name)
                arcname = os.path.relpath(fpath, repo_root)
                zf.write(fpath, arcname)
                n_files += 1

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print('Wrote %s' % out_path)
    print('%d files, %.1f MB' % (n_files, size_mb))
    print('Upload it to the ROOT of your Google Drive (My Drive/).')


if __name__ == '__main__':
    main()
