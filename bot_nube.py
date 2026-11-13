import os
import threading
import time
from flask import Flask
import requests

app = Flask(__name__)

# Reemplaza con tu token o usa variables de entorno en la nube
TOKEN = os.environ.get("6064688645", "9209835663:AAG55478xKnZapcVVmKZ-bsebAca00XqLLc")


@app.route("/")
def home():
  return "🤖 ¡El bot de recordatorios en la nube está activo 24/7!"


def send_telegram_msg(chat_id, text):
  try:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=10)
  except Exception as e:
    print(f"Error enviando mensaje: {e}")


def run_timer(chat_id, task, delay_seconds):
  time.sleep(delay_seconds)
  send_telegram_msg(
      chat_id,
      f"🚨 *¡RECORDATORIO EN LA NUBE!*\n\nEs hora de hacer: *{task}*",
  )


def poll_telegram():
  print("🤖 Bot en la nube iniciado y escuchando Telegram...")
  offset = 0
  while True:
    try:
      url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={offset}&timeout=25"
      response = requests.get(url, timeout=30)
      if response.ok:
        data = response.json()
        for result in data.get("result", []):
          offset = result["update_id"] + 1
          message = result.get("message", {})
          chat_id = str(message.get("chat", {}).get("id", ""))
          text = message.get("text", "").strip()

          if text.startswith("/rec") or text.startswith("/recordatorio"):
            parts = text.split(maxsplit=3)
            if len(parts) >= 4:
              _, amt_str, unit_raw, task = parts
              try:
                amount = float(amt_str)
                if "min" in unit_raw.lower():
                  delay_seconds = int(amount * 60)
                  unit = "Minutos"
                elif "dia" in unit_raw.lower() or "dias" in unit_raw.lower():
                  delay_seconds = int(amount * 86400)
                  unit = "Días"
                else:
                  delay_seconds = int(amount * 3600)
                  unit = "Horas"

                # Iniciar el temporizador en segundo plano
                threading.Thread(
                    target=run_timer,
                    args=(chat_id, task, delay_seconds),
                    daemon=True,
                ).start()

                send_telegram_msg(
                    chat_id,
                    f"✅ *¡Recordatorio programado!*\n📌 Tarea: {task}\n⏱️ Tiempo: {amount} {unit}",
                )
              except ValueError:
                send_telegram_msg(
                    chat_id,
                    "⚠️ Formato incorrecto. Usa: `/rec [número]"
                    " [Minutos/Horas/Días] [Mensaje]`",
                )
    except Exception as e:
      print(f"Error en polling: {e}")
    time.sleep(3)


if __name__ == "__main__":
  # Iniciar el bot de Telegram en un hilo secundario
  threading.Thread(target=poll_telegram, daemon=True).start()

  # Iniciar Flask (Render le asigna el puerto automáticamente)
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)