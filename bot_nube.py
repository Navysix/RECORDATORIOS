import os
import threading
import time
from flask import Flask, jsonify
import requests

app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_BOT_TOKEN_AQUÍ")

# Lista en memoria para guardar los pendientes activos en la nube
active_cloud_reminders = []


@app.route("/")
def home():
  return "🤖 ¡El bot de recordatorios en la nube está activo 24/7!"


@app.route("/reminders")
def get_reminders():
  # Endpoint para que la PC descargue los recordatorios pendientes
  return jsonify(active_cloud_reminders)


def send_telegram_msg(chat_id, text):
  try:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=10)
  except Exception as e:
    print(f"Error enviando mensaje: {e}")


def run_timer(task, delay_seconds, display_text, chat_id):
  time.sleep(delay_seconds)
  send_telegram_msg(
      chat_id,
      f"🚨 *¡RECORDATORIO EN LA NUBE!*\n\nEs hora de hacer: *{task}*",
  )
  # Al cumplirse, lo borramos de la lista en la nube
  global active_cloud_reminders
  active_cloud_reminders = [
      r for r in active_cloud_reminders if r["display_text"] != display_text
  ]


def poll_telegram():
  print("🤖 Bot en la nube iniciado y escuchando Telegram...")
  offset = 0
  global active_cloud_reminders
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
                  delay_seconds = amount * 60
                  display_time = f"{amount} min"
                elif "dia" in unit_raw.lower() or "dias" in unit_raw.lower():
                  delay_seconds = amount * 86400
                  display_time = f"{amount} días"
                else:
                  delay_seconds = amount * 3600
                  display_time = f"{amount} h"

                display_text = f"⏳ {task} ({display_time})"
                target_time = time.time() + delay_seconds

                reminder_obj = {
                    "task": task,
                    "target_time": target_time,
                    "display_text": display_text,
                    "chat_id": chat_id,
                }

                active_cloud_reminders.append(reminder_obj)

                # Iniciar temporizador en la nube
                threading.Thread(
                    target=run_timer,
                    args=(task, delay_seconds, display_text, chat_id),
                    daemon=True,
                ).start()

                send_telegram_msg(
                    chat_id,
                    f"✅ *¡Recordatorio registrado en la nube!*\n📌 Tarea: {task}\n⏱️ Tiempo: {display_time}",
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
  threading.Thread(target=poll_telegram, daemon=True).start()
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)