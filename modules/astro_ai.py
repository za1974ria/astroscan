# -*- coding: utf-8 -*-
"""
Module Astro AI — explication d'objets célestes.
Aucune dépendance externe, pas d'appel API.
"""


def explain_object(name):
    """Retourne une description simple d'un objet spatial (nom ou vide)."""
    name = (name or '').strip()
    if not name:
        return {
            'ok': False,
            'name': '',
            'description': 'Aucun nom d\'objet fourni.',
        }
    # Réponses statiques pour quelques objets courants
    known = {
        'mars': 'Planète tellurique, quatrième du Système solaire. Atmosphère ténue, deux satellites : Phobos et Deimos.',
        'jupiter': 'Géante gazeuse, cinquième planète. Grande tache rouge, plus de 79 lunes connues.',
        'saturn': 'Géante gazeuse avec anneaux visibles. Deuxième plus grande planète du Système solaire.',
        'iss': 'Station spatiale internationale en orbite basse. Laboratoire habité en permanence.',
        'moon': 'Unique satellite naturel de la Terre. Phase et éclipses observables.',
        'lune': 'Unique satellite naturel de la Terre. Phase et éclipses observables.',
        'andromeda': 'Galaxie d\'Andromède (M31), galaxie spirale la plus proche de la Voie lactée.',
        'orion': 'Constellation et nébuleuse d\'Orion (M42), région de formation stellaire.',
    }
    key = name.lower()
    description = known.get(key)
    if not description:
        description = f"Objet céleste « {name} » — description en cours d'intégration."
    return {
        'ok': True,
        'name': name,
        'description': description,
    }
