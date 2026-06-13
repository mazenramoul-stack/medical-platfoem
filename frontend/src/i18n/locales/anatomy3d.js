// Strings for the interactive 3D anatomy result panel (Anatomy3DPanel).
export default {
  en: {
    title: 'Anatomical view',
    rotateHint: 'Drag to rotate · scroll to zoom',
    implicated: 'Implicated structure',
    caveat:
      'Schematic highlight of the implicated structure — not a registered localization. '
      + 'Decision-support only, not a diagnosis.',
    none: 'No localized conduction abnormality detected.',
    rateNote: 'Rate finding — not localized to a myocardial wall.',
    measuredRate: 'Beating at the measured rate ({bpm} bpm)',
    severity: { high: 'High', medium: 'Moderate', low: 'Low' },
    regions: {
      lv: 'Left ventricle',
      rv: 'Right ventricle',
      la: 'Left atrium',
      ra: 'Right atrium',
      'av-node': 'AV node',
      'sa-node': 'SA node',
    },
    findings: {
      RBBB: 'Right bundle branch — right-ventricular conduction',
      LBBB: 'Left bundle branch — left-ventricular conduction',
      PVC: 'Ectopic ventricular origin',
      AFIB: 'Atrial fibrillation — atrial rhythm',
      '1AVB': 'First-degree AV block — nodal conduction delay',
      STACH: 'Sinus tachycardia — rate',
      SBRAD: 'Sinus bradycardia — rate',
    },
  },
  fr: {
    title: 'Vue anatomique',
    rotateHint: 'Glisser pour pivoter · molette pour zoomer',
    implicated: 'Structure impliquée',
    caveat:
      'Mise en évidence schématique de la structure impliquée — pas une localisation enregistrée. '
      + 'Aide à la décision, pas un diagnostic.',
    none: 'Aucune anomalie de conduction localisée détectée.',
    rateNote: 'Anomalie de fréquence — non localisée à une paroi myocardique.',
    measuredRate: 'Battant au rythme mesuré ({bpm} bpm)',
    severity: { high: 'Élevée', medium: 'Modérée', low: 'Faible' },
    regions: {
      lv: 'Ventricule gauche',
      rv: 'Ventricule droit',
      la: 'Oreillette gauche',
      ra: 'Oreillette droite',
      'av-node': 'Nœud AV',
      'sa-node': 'Nœud SA',
    },
    findings: {
      RBBB: 'Bloc de branche droit — conduction ventriculaire droite',
      LBBB: 'Bloc de branche gauche — conduction ventriculaire gauche',
      PVC: 'Origine ventriculaire ectopique',
      AFIB: 'Fibrillation auriculaire — rythme auriculaire',
      '1AVB': 'Bloc AV du premier degré — retard de conduction nodal',
      STACH: 'Tachycardie sinusale — fréquence',
      SBRAD: 'Bradycardie sinusale — fréquence',
    },
  },
};
