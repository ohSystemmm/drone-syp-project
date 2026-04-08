import socket


class TelloLEDController:
    def __init__(self, ip='192.168.10.1', port=8889):
        self.tello_address = (ip, port)
        # UDP-Socket einrichten
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Kurzer Timeout, damit die GUI nicht blockiert, falls wir doch mal auf Antworten warten
        self.sock.settimeout(0.5)

        # Drohne beim Start direkt in den SDK-Modus versetzen
        self.enable_sdk()

    def send_command(self, cmd):
        """Sendet einen rohen Befehl an die Drohne."""
        try:
            self.sock.sendto(cmd.encode('utf-8'), self.tello_address)
            print(f"[Backend] Gesendet: {cmd}")
        except Exception as e:
            print(f"[Backend] Fehler beim Senden: {e}")

    def enable_sdk(self):
        """Aktiviert den Programmiermodus der Tello."""
        self.send_command("command")

    def send_pattern(self, pattern: str):
        """
        Sendet einen 64-stelligen String an die LED-Matrix.
        Gültige Zeichen: '0' (Aus), 'r' (Rot), 'b' (Blau), 'p' (Lila).
        """
        if len(pattern) != 64:
            print(f"[Backend] Fehler: Muster muss exakt 64 Zeichen haben (aktuell {len(pattern)}).")
            return

        cmd = f"EXT mled g {pattern}"
        self.send_command(cmd)

    def clear_matrix(self):
        """Schaltet alle LEDs auf dem Feld aus."""
        leeres_muster = "0" * 64
        self.send_pattern(leeres_muster)

    def send_text(self, text: str, color='r', direction='l', speed=2.5):
        """
        Lässt einen Text über das Display scrollen.
        Richtung: 'l' (links), 'r' (rechts), 'u' (oben), 'd' (unten)
        Farbe: 'r' (rot), 'b' (blau), 'p' (lila)
        """
        cmd = f"EXT mled {direction} {color} {speed} {text}"
        self.send_command(cmd)