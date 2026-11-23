import os
import threading
import time
import uuid
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

VALID_CATEGORIES = [
    "Alta Demanda",
    "Prioridad",
    "Acuérdate!",
    "No se te olvide!!",
]

active_cloud_reminders = []
reminders_lock = threading.Lock()


def normalize_category(raw_cat):
  if not raw_cat:
    return "Alta Demanda"
  clean = str(raw_cat).strip().lower()
  for cat in VALID_CATEGORIES:
    if cat.lower() == clean:
      return cat
  if "prior" in clean:
    return "Prioridad"
  if "acuerd" in clean:
    return "Acuérdate!"
  if "olvid" in clean:
    return "No se te olvide!!"
  return "Alta Demanda"


def compute_delay_and_label(amount, unit):
  u = str(unit or "Minutos").strip().lower()
  if "hora" in u:
    return amount * 3600.0, f"{amount:g} h"
  if "dia" in u or "día" in u:
    return amount * 86400.0, f"{amount:g} días"
  return amount * 60.0, f"{amount:g} min"


def cleanup_expired():
  now = time.time()
  with reminders_lock:
    global active_cloud_reminders
    active_cloud_reminders = [
        r for r in active_cloud_reminders if r["target_time"] > now
    ]


def schedule_removal(reminder_id, delay_seconds):
  def worker():
    time.sleep(max(0.0, delay_seconds))
    with reminders_lock:
      global active_cloud_reminders
      active_cloud_reminders = [
          r for r in active_cloud_reminders if r["id"] != reminder_id
      ]

  threading.Thread(target=worker, daemon=True).start()


PHONE_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Recordatorios - Móvil</title>
  <style>
    body {
      font-family: system-ui, -apple-system, sans-serif;
      background: #1e1e2f;
      color: #ffffff;
      margin: 0;
      padding: 18px;
    }
    .card {
      max-width: 460px;
      margin: 0 auto;
      background: #252538;
      border-radius: 12px;
      padding: 18px;
      border: 1px solid #3e3e5c;
    }
    h1 { font-size: 1.25rem; margin: 0 0 14px; }
    label { display: block; font-size: 0.85rem; color: #b0b0c0; margin-top: 10px; }
    input, select, button {
      width: 100%;
      box-sizing: border-box;
      margin-top: 5px;
      padding: 10px;
      border-radius: 8px;
      border: none;
      font-size: 0.95rem;
    }
    input, select { background: #2d2d44; color: #fff; }
    .row { display: flex; gap: 8px; }
    .row > * { flex: 1; }
    button {
      background: #4e4376;
      color: #fff;
      font-weight: 700;
      margin-top: 14px;
      cursor: pointer;
    }
    .item {
      background: #2d2d44;
      padding: 10px 12px;
      border-radius: 8px;
      margin-top: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }
    .cat { font-size: 0.78rem; color: #c7c2e8; }
    .del {
      width: auto;
      margin: 0;
      padding: 6px 10px;
      background: #6b2d3b;
      font-size: 0.8rem;
    }
    h2 { font-size: 1rem; margin-top: 20px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Recordatorios (Móvil)</h1>
    <form id="remForm">
      <label for="task">¿Qué quieres recordar?</label>
      <input id="task" name="task" required placeholder="Ej. Revisar avance del proyecto" />

      <div class="row">
        <div>
          <label for="amount">Tiempo de espera</label>
          <input id="amount" name="amount" type="number" step="any" min="0.1" required placeholder="15" />
        </div>
        <div>
          <label for="unit">Unidad</label>
          <select id="unit" name="unit">
            <option value="Minutos">Minutos</option>
            <option value="Horas">Horas</option>
            <option value="Días">Días</option>
          </select>
        </div>
      </div>

      <label for="category">Categoría</label>
      <select id="category" name="category">
        <option value="Alta Demanda">Alta Demanda</option>
        <option value="Prioridad">Prioridad</option>
        <option value="Acuérdate!">Acuérdate!</option>
        <option value="No se te olvide!!">No se te olvide!!</option>
      </select>

      <button type="submit">Enviar a la nube</button>
    </form>

    <h2>Activos en la nube</h2>
    <div id="list"></div>
  </div>

  <script>
    async function loadList() {
      const res = await fetch('/api/reminders');
      const items = await res.json();
      const container = document.getElementById('list');
      container.innerHTML = '';
      if (!items.length) {
        container.innerHTML = '<p style="color:#b0b0c0;font-size:0.9rem;">No hay pendientes activos.</p>';
        return;
      }
      for (const r of items) {
        const div = document.createElement('div');
        div.className = 'item';
        div.innerHTML = `
          <div>
            <div><strong>${r.display_text}</strong></div>
            <div class="cat">${r.category}</div>
          </div>
          <button class="del" onclick="removeItem('${r.id}')">Listo</button>
        `;
        container.appendChild(div);
      }
    }

    async function removeItem(id) {
      await fetch('/api/reminders/' + encodeURIComponent(id), { method: 'DELETE' });
      loadList();
    }

    document.getElementById('remForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        task: document.getElementById('task').value.trim(),
        amount: parseFloat(document.getElementById('amount').value),
        unit: document.getElementById('unit').value,
        category: document.getElementById('category').value,
      };
      const res = await fetch('/api/reminders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        document.getElementById('task').value = '';
        document.getElementById('amount').value = '';
        loadList();
      }
    });

    loadList();
    setInterval(loadList, 5000);
  </script>
</body>
</html>
"""


@app.route("/")
def home():
  return render_template_string(PHONE_HTML)


@app.route("/reminders")
@app.route("/api/reminders", methods=["GET"])
def get_reminders():
  cleanup_expired()
  with reminders_lock:
    return jsonify(list(active_cloud_reminders))


@app.route("/api/reminders", methods=["POST"])
def create_reminder():
  data = request.get_json(silent=True) or request.form
  task = str(data.get("task", "")).strip()
  unit = data.get("unit", "Minutos")
  category = normalize_category(data.get("category"))

  try:
    amount = float(data.get("amount", 0))
  except (TypeError, ValueError):
    return jsonify({"error": "Tiempo inválido"}), 400

  if not task or amount <= 0:
    return jsonify({"error": "Falta tarea o tiempo mayor a 0"}), 400

  delay_seconds, display_time = compute_delay_and_label(amount, unit)
  reminder_id = str(uuid.uuid4())
  reminder_obj = {
      "id": reminder_id,
      "task": task,
      "target_time": time.time() + delay_seconds,
      "display_text": f"⏳ {task} ({display_time})",
      "category": category,
  }

  with reminders_lock:
    active_cloud_reminders.append(reminder_obj)

  schedule_removal(reminder_id, delay_seconds)
  return jsonify(reminder_obj), 201


@app.route("/api/reminders/<reminder_id>", methods=["DELETE"])
def delete_reminder(reminder_id):
  with reminders_lock:
    global active_cloud_reminders
    before = len(active_cloud_reminders)
    active_cloud_reminders = [
        r for r in active_cloud_reminders if r["id"] != reminder_id
    ]
    deleted = len(active_cloud_reminders) < before
  return jsonify({"deleted": deleted}), (200 if deleted else 404)


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)