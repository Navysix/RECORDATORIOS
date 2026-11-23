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
cloud_history = []
state_lock = threading.Lock()


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


def format_time_ago(created_at):
  if not created_at:
    return "Hace un momento"
  elapsed = max(0, int(time.time() - float(created_at)))
  if elapsed < 60:
    return "Hace unos segundos"
  minutes = elapsed // 60
  if minutes < 60:
    return f"Hace {minutes} {'Minuto' if minutes == 1 else 'Minutos'}"
  hours = minutes // 60
  if hours < 24:
    return f"Hace {hours} {'Hora' if hours == 1 else 'Horas'}"
  days = hours // 24
  return f"Hace {days} {'Día' if days == 1 else 'Días'}"


def record_history_item(task, category, status="Registrado", created_at=None):
  entry = {
      "id": str(uuid.uuid4()),
      "task": task,
      "category": normalize_category(category),
      "status": status,
      "created_at": created_at or time.time(),
  }
  with state_lock:
    global cloud_history
    cloud_history = [
        h
        for h in cloud_history
        if not (
            h["task"] == entry["task"]
            and h["category"] == entry["category"]
            and abs(h["created_at"] - entry["created_at"]) < 2
        )
    ]
    cloud_history.insert(0, entry)
    cloud_history = cloud_history[:100]
  return entry


def cleanup_expired():
  now = time.time()
  expired_items = []
  with state_lock:
    global active_cloud_reminders
    still_active = []
    for r in active_cloud_reminders:
      if r["target_time"] > now:
        still_active.append(r)
      else:
        expired_items.append(r)
    active_cloud_reminders = still_active

  for item in expired_items:
    record_history_item(
        item["task"],
        item.get("category"),
        status="Cumplido",
        created_at=item.get("created_at", now),
    )


def schedule_removal(reminder_id, delay_seconds, task, category, created_at):
  def worker():
    time.sleep(max(0.0, delay_seconds))
    with state_lock:
      global active_cloud_reminders
      found = None
      remaining = []
      for r in active_cloud_reminders:
        if r["id"] == reminder_id:
          found = r
        else:
          remaining.append(r)
      active_cloud_reminders = remaining
    if found:
      record_history_item(task, category, status="Cumplido", created_at=created_at)

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
      max-width: 480px;
      margin: 0 auto;
      background: #252538;
      border-radius: 12px;
      padding: 18px;
      border: 1px solid #3e3e5c;
    }
    h1 { font-size: 1.25rem; margin: 0 0 14px; }
    h2 { font-size: 1.05rem; margin: 22px 0 10px; border-top: 1px solid #3e3e5c; padding-top: 14px; }
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
    button.primary {
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
    .cat { font-size: 0.8rem; color: #67e8f9; margin-top: 3px; font-weight: 600; }
    .del {
      width: auto;
      margin: 0;
      padding: 6px 10px;
      background: #6b2d3b;
      color: #fff;
      font-weight: 700;
      border-radius: 7px;
      border: none;
      font-size: 0.8rem;
      cursor: pointer;
    }
    .hist-item {
      background: #2d2d44;
      padding: 10px 12px;
      border-radius: 8px;
      margin-top: 8px;
      font-size: 0.9rem;
      line-height: 1.4;
      word-break: break-word;
    }
    .color-task { color: #fde047; font-weight: 700; }
    .color-cat { color: #67e8f9; font-weight: 700; }
    .color-time { color: #f472b6; font-weight: 600; }
    .sep { color: #9ca3af; margin: 0 5px; }
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

      <button class="primary" type="submit">Enviar a la nube</button>
    </form>

    <h2>Activos en la nube</h2>
    <div id="list"></div>

    <h2>Historial</h2>
    <div id="historyList"></div>
  </div>

  <script>
    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text || '';
      return div.innerHTML;
    }

    async function loadActive() {
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
            <div class="color-task">${escapeHtml(r.display_text)}</div>
            <div class="cat">${escapeHtml(r.category)}</div>
          </div>
          <button class="del" onclick="removeItem('${escapeHtml(r.id)}')">Listo</button>
        `;
        container.appendChild(div);
      }
    }

    async function loadHistory() {
      const res = await fetch('/api/history');
      const items = await res.json();
      const container = document.getElementById('historyList');
      container.innerHTML = '';
      if (!items.length) {
        container.innerHTML = '<p style="color:#b0b0c0;font-size:0.9rem;">Aún no hay recordatorios en el historial.</p>';
        return;
      }
      for (const h of items) {
        const div = document.createElement('div');
        div.className = 'hist-item';
        div.innerHTML = `
          <span class="color-task">"${escapeHtml(h.task)}"</span>
          <span class="sep">-</span>
          <span class="color-cat">"${escapeHtml(h.category)}"</span>
          <span class="sep">-</span>
          <span class="color-time">"${escapeHtml(h.time_ago)}"</span>
        `;
        container.appendChild(div);
      }
    }

    async function removeItem(id) {
      await fetch('/api/reminders/' + encodeURIComponent(id), { method: 'DELETE' });
      await refreshAll();
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
        await refreshAll();
      }
    });

    async function refreshAll() {
      await Promise.all([loadActive(), loadHistory()]);
    }

    refreshAll();
    setInterval(refreshAll, 5000);
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
  with state_lock:
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
  now = time.time()
  reminder_id = str(uuid.uuid4())
  reminder_obj = {
      "id": reminder_id,
      "task": task,
      "created_at": now,
      "target_time": now + delay_seconds,
      "display_text": f"⏳ {task} ({display_time})",
      "category": category,
  }

  with state_lock:
    active_cloud_reminders.append(reminder_obj)

  record_history_item(task, category, status="Registrado", created_at=now)
  schedule_removal(reminder_id, delay_seconds, task, category, now)
  return jsonify(reminder_obj), 201


@app.route("/api/reminders/<reminder_id>", methods=["DELETE"])
def delete_reminder(reminder_id):
  removed = None
  with state_lock:
    global active_cloud_reminders
    remaining = []
    for r in active_cloud_reminders:
      if r["id"] == reminder_id and removed is None:
        removed = r
      else:
        remaining.append(r)
    active_cloud_reminders = remaining

  if removed:
    record_history_item(
        removed["task"],
        removed.get("category"),
        status="Eliminado",
        created_at=removed.get("created_at", time.time()),
    )
    return jsonify({"deleted": True}), 200
  return jsonify({"deleted": False}), 404


@app.route("/api/history", methods=["GET", "POST"])
def handle_history():
  cleanup_expired()
  if request.method == "POST":
    data = request.get_json(silent=True) or {}
    task = str(data.get("task", "")).strip()
    if not task:
      return jsonify({"error": "Falta tarea"}), 400
    category = normalize_category(data.get("category"))
    status = str(data.get("status", "Registrado")).strip() or "Registrado"
    created_at = data.get("created_at")
    try:
      created_at = float(created_at) if created_at is not None else time.time()
    except (TypeError, ValueError):
      created_at = time.time()

    entry = record_history_item(task, category, status=status, created_at=created_at)
    return jsonify(entry), 201

  with state_lock:
    formatted = [
        {
            "id": h["id"],
            "task": h["task"],
            "category": h["category"],
            "status": h["status"],
            "time_ago": format_time_ago(h.get("created_at")),
        }
        for h in cloud_history
    ]
  return jsonify(formatted)


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)