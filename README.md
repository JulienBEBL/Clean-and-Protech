🧼 Système d’automatisation de nettoyage de canalisation

Projet d’automatisation d’un système de nettoyage de chauffage collectif basé sur un Raspberry Pi 4B (4Go).
Le système pilote plusieurs vannes motorisées, électrovannes, un variateur de pompe, ainsi qu’une interface utilisateur complète (LCD, boutons, sélecteurs, LEDs).

🚀 Fonctionnalités principales

Pilotage de 8 vannes motorisées via drivers DM542T et registre à décalage SN74HC595 (DIR + PUL).

Vanne 4 voies avec gestion des positions séquentielles.

Injection d’air comprimé avec plusieurs modes (OFF, pulsé 2s/4s, continu).

Gestion pompe via relais déclencheur connecté à une entrée I/O du variateur (démarrage/arrêt sécurisé).

Débitmètre avec calcul en temps réel du débit (L/min) et du volume cumulé (L).

Interface utilisateur :

LCD I²C 16x2

Boutons programmes (1 à 6)

Sélecteur vanne 4 voies (5 positions)

Bouton Air pour cycle des modes

LEDs indiquant l’état de l’air

Sécurité intégrée :

Mise à zéro des moteurs (MAZ) en initialisation

Fermeture automatique de toutes les vannes (sauf V4V) en fin de programme

Affichage du volume total avant arrêt machine

Gestion “safe shutdown” (arrêt propre en cas d’erreur ou Ctrl+C)

📂 Organisation du code

main.py : programme principal, gestion complète du système

lib/ : librairies spécifiques

MCP3008_0.py, MCP3008_1.py → gestion des entrées analogiques (boutons, sélecteur)

LCDI2C_backpack/ → gestion de l’écran LCD I²C

tests/ : scripts unitaires pour vérifier chaque sous-système indépendamment

test_moteurs.py

test_leds.py

test_boutons.py

test_lcd.py

test_relais.py

test_debitmetre.py

runner.py → mini-runner pour lancer un test rapidement

🔧 Matériel utilisé

Raspberry Pi 4B (4Go)

Drivers moteurs DM542T

SN74HC595N (x2) – registres à décalage pour DIR/LEDs

Moteurs pas-à-pas + vannes motorisées

Relais 24V pour variateur de pompe

Électrovanne air comprimé

Débitmètre à effet Hall

Écran LCD I²C 16x2

Boutons poussoirs + sélecteur rotatif 5 voies

⚡ Installation

Cloner le dépôt :

git clone https://github.com/USERNAME/cleaning-automation.git
cd cleaning-automation


Installer les dépendances Python :

sudo apt update
sudo apt install python3-rpi.gpio python3-smbus i2c-tools


Activer SPI et I²C sur le Raspberry Pi :

sudo raspi-config


Lancer le programme principal :

python3 main.py

🧪 Tests unitaires

Chaque composant matériel peut être validé indépendamment :

python3 tests/test_moteurs.py
python3 tests/test_leds.py
python3 tests/test_boutons.py
python3 tests/test_lcd.py
python3 tests/test_relais.py
python3 tests/test_debitmetre.py

🛡️ Sécurité & bonnes pratiques

Ne jamais lancer la pompe sans s’assurer que les vannes sont dans la bonne configuration.

Débrancher l’alimentation des moteurs avant intervention mécanique.

Les programmes de nettoyage doivent être confirmés par l’opérateur (double appui bouton).

📜 Licence

Projet développé dans le cadre de BEBL / Clean&Protech.
Licence à définir (privée ou open source selon contexte).
