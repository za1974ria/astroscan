import json, os, subprocess

MESSIER = [
    {'id':'M1','nom':'Nébuleuse du Crabe','type':'Nébuleuse supernova','constellation':'Taureau','distance_al':6500,'magnitude':8.4,'ra':'05h 34m 32s','dec':'+22° 00\''},
    {'id':'M8','nom':'Nébuleuse de la Lagune','type':'Nébuleuse émission','constellation':'Sagittaire','distance_al':4100,'magnitude':6.0,'ra':'18h 03m 37s','dec':'-24° 23\''},
    {'id':'M13','nom':'Grand Amas d\'Hercule','type':'Amas globulaire','constellation':'Hercule','distance_al':25100,'magnitude':5.8,'ra':'16h 41m 41s','dec':'+36° 28\''},
    {'id':'M31','nom':'Galaxie d\'Andromède','type':'Galaxie spirale','constellation':'Andromède','distance_al':2537000,'magnitude':3.4,'ra':'00h 42m 44s','dec':'+41° 16\''},
    {'id':'M42','nom':'Nébuleuse d\'Orion','type':'Nébuleuse émission','constellation':'Orion','distance_al':1344,'magnitude':4.0,'ra':'05h 35m 17s','dec':'-05° 23\''},
    {'id':'M45','nom':'Pléiades','type':'Amas ouvert','constellation':'Taureau','distance_al':444,'magnitude':1.6,'ra':'03h 47m 24s','dec':'+24° 07\''},
    {'id':'M51','nom':'Galaxie du Tourbillon','type':'Galaxie spirale','constellation':'Chiens de Chasse','distance_al':23000000,'magnitude':8.4,'ra':'13h 29m 53s','dec':'+47° 12\''},
    {'id':'M57','nom':'Nébuleuse de la Lyre','type':'Nébuleuse planétaire','constellation':'Lyre','distance_al':2300,'magnitude':8.8,'ra':'18h 53m 35s','dec':'+33° 02\''},
    {'id':'M63','nom':'Galaxie du Tournesol','type':'Galaxie spirale','constellation':'Chiens de Chasse','distance_al':37000000,'magnitude':8.6,'ra':'13h 15m 49s','dec':'+42° 02\''},
    {'id':'M64','nom':'Galaxie de l\'Oeil Noir','type':'Galaxie spirale','constellation':'Chevelure de Bérénice','distance_al':17000000,'magnitude':8.5,'ra':'12h 56m 44s','dec':'+21° 41\''},
    {'id':'M78','nom':'Nébuleuse M78','type':'Nébuleuse réflexion','constellation':'Orion','distance_al':1600,'magnitude':8.3,'ra':'05h 46m 46s','dec':'+00° 05\''},
    {'id':'M81','nom':'Galaxie de Bode','type':'Galaxie spirale','constellation':'Grande Ourse','distance_al':11800000,'magnitude':6.9,'ra':'09h 55m 33s','dec':'+69° 04\''},
    {'id':'M82','nom':'Galaxie du Cigare','type':'Galaxie irrégulière','constellation':'Grande Ourse','distance_al':11500000,'magnitude':8.4,'ra':'09h 55m 52s','dec':'+69° 41\''},
    {'id':'M101','nom':'Galaxie du Moulinet','type':'Galaxie spirale','constellation':'Grande Ourse','distance_al':20900000,'magnitude':7.9,'ra':'14h 03m 12s','dec':'+54° 21\''},
    {'id':'M104','nom':'Galaxie Sombrero','type':'Galaxie spirale','constellation':'Vierge','distance_al':29300000,'magnitude':8.0,'ra':'12h 39m 59s','dec':'-11° 37\''},
]

def search_catalog(query='', type_filter=''):
    results = MESSIER
    if query:
        q = query.lower()
        results = [o for o in results if q in o['nom'].lower() or q in o['id'].lower() or q in o['constellation'].lower()]
    if type_filter:
        results = [o for o in results if type_filter.lower() in o['type'].lower()]
    return results

def get_object(obj_id):
    for o in MESSIER:
        if o['id'].upper() == obj_id.upper():
            return o
    return None
