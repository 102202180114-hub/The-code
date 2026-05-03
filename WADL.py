import os, random, time, socket, qrcode, webbrowser, pandas as pd
from flask import Flask, render_template, request, jsonify

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0] 
    except: IP = '127.0.0.1'
    finally: s.close()
    return IP

LOCAL_IP = get_ip()
BASE_URL = f"http://{LOCAL_IP}:5000"
SAVE_DIR = "EEG Arithmatic and Focus Exam"

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs('templates', exist_ok=True)
qrcode.make(f"{BASE_URL}/remote").save("static/qr.png")

laptop_html = """
<!DOCTYPE html>
<html>
<head><title>EEG Display</title><style>
    body { transition: background-color 0.3s; font-family: sans-serif; text-align: center; height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; overflow: hidden; }
    #plus { font-weight: bold; transition: all 0.1s; line-height: 1; }
    #math { font-size: 120px; font-weight: bold; }
    #setup { background: white; padding: 40px; border-radius: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); color: #d63384; }
    .status-text { margin-top: 15px; font-weight: bold; font-size: 1.2em; color: #ff69b4; }
    .msg { position: fixed; top: 20px; background: #4CAF50; color: white; padding: 15px 30px; border-radius: 50px; display: none; z-index:100; font-weight: bold; }
    .fs-btn { margin-top: 20px; padding: 10px 20px; border-radius: 20px; background: #ff85a2; color: white; border: none; cursor: pointer; }
</style></head>
<body id="bg">
    <div id="msg" class="msg">️ Connected! Starting Setup...</div>
    <div id="setup">
        <h2>Scan to Connect Remote</h2>
        <img src="/static/qr.png" width="280">
        <div id="status" class="status-text">⏳ Waiting for Connection...</div>
        <button class="fs-btn" onclick="toggleFS()">️ Enter Full Screen Mode</button>
        <p style="color:#888; font-size: 0.8em;">IP: """ + LOCAL_IP + """</p>
    </div>
    <div id="display" style="display:none"></div>
<script>
    let connected = false;
    function toggleFS() { if (!document.fullscreenElement) { document.documentElement.requestFullscreen(); } }
    async function loop() {
        try {
            const res = await fetch('/get_state'); const data = await res.json();
            if (data.mode === 'reset_trigger') { location.reload(); return; }
            document.getElementById('bg').style.backgroundColor = data.bg_color;
            if (data.connected && !connected) {
                connected = true;
                document.getElementById('status').innerText = "Connected!";
                document.getElementById('msg').style.display = "block";
                setTimeout(() => {
                    document.getElementById('msg').style.display = 'none';
                    document.getElementById('setup').style.display = 'none'; 
                    document.getElementById('display').style.display = 'block';
                }, 1500);
            }
            if (connected) {
                const disp = document.getElementById('display');
                if (data.mode === 'plus') disp.innerHTML = `<div id="plus" style="font-size:${data.size}px; color:${data.color}">+</div>`;
                else if (data.mode === 'math') disp.innerHTML = `<div id="math" style="color:${data.color}">${data.problem}</div>`;
                else if (data.mode === 'finish') disp.innerHTML = '<h1>Research Complete</h1>';
            }
        } catch (e) { console.log("Waiting for server..."); }
        setTimeout(loop, 300);
    }
    loop();
</script></body></html>
"""

remote_html = """
<!DOCTYPE html>
<html><head><title>EEG Remote</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    body { background: #fff5f8; font-family: sans-serif; text-align: center; padding: 20px; color: #d63384; }
    .card { background: white; padding: 15px; border-radius: 20px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
    .btn { background: #ff85a2; border: none; padding: 15px; border-radius: 50px; color: white; width: 100%; font-size: 1.2em; cursor: pointer; font-weight: bold; margin-top: 10px; }
    #preview { border: 2px dashed #ffdae0; border-radius: 15px; height: 100px; display: flex; align-items: center; justify-content: center; margin: 10px 0; }
    input { font-size: 1.1em; width: 85%; text-align: center; border: 2px solid #ffdae0; border-radius: 10px; padding: 10px; margin: 10px; }
    input[type=range] { width: 90%; }
</style></head>
<body><div id="ui">
    <div class="card">
        <h3>Style Preview & Setup</h3>
        <div id="preview"><span id="pre-plus">+</span></div>
        <input type="text" id="fname" placeholder="Enter Participant Name">
        Size: <input type="range" id="sz" min="50" max="600" value="200" oninput="upd()"><br>
        Plus Color: <input type="color" id="clr" value="#d63384" onchange="upd()"><br>
        Laptop BG: <input type="color" id="bg_clr" value="#fff5f8" onchange="upd()">
    </div>
    <button class="btn" onclick="startStudy()">Start Phase 1</button>
</div><script>
    let stage = 0; let pIdx = 0; let probs = [];
    async function upd() {
        const s = document.getElementById('sz').value; const c = document.getElementById('clr').value; const bg = document.getElementById('bg_clr').value;
        document.getElementById('preview').style.backgroundColor = bg;
        document.getElementById('pre-plus').style.fontSize = (s/5) + "px";
        document.getElementById('pre-plus').style.color = c;
        await fetch('/update_style', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({size:s, color:c, bg_color:bg})});
    }
    async function startStudy() {
        const name = document.getElementById('fname').value || "Unnamed";
        await fetch('/init_study', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({filename:name})});
        next();
    }
    async function next() {
        stage++;
        if (stage === 2 || stage === 4) { startMath(); }
        else if (stage === 6) { 
            await fetch('/set_mode', {method:'POST', body:JSON.stringify({mode:'finish'}), headers:{'Content-Type':'application/json'}}); 
            document.getElementById('ui').innerHTML="<div class='card'><h2>Study Finished!</h2><button class='btn' onclick='resetAll()'>Restart for Next Participant</button></div>"; 
        }
        else { await fetch('/set_mode', {method:'POST', body:JSON.stringify({mode:'plus'}), headers:{'Content-Type':'application/json'}}); renderPlus(); }
    }
    async function startMath() {
        const res = await fetch('/gen_math', {method:'POST'}); probs = await res.json(); pIdx = 0; renderMath();
    }
    function renderMath() {
        document.getElementById('ui').innerHTML = `<div class="card"><h3>Test ${stage/2}</h3><p style="font-size:2.5em">${probs[pIdx].q}</p><input type="number" id="ans" inputmode="numeric" autofocus></div><button class="btn" onclick="sub()">Submit</button>`;
        setTimeout(() => document.getElementById('ans').focus(), 100);
    }
    async function sub() {
        const a = document.getElementById('ans').value || "0"; pIdx++;
        if (pIdx < 10) { await fetch('/upd_math', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({prob:probs[pIdx].q, ans:a})}); renderMath(); }
        else { await fetch('/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ans:a, test_num: stage/2})}); next(); }
    }
    function renderPlus() { document.getElementById('ui').innerHTML = `<div class="card"><h3>Phase ${stage}</h3><button class="btn" onclick="next()">Next Stage</button></div>`; }
    async function resetAll() { await fetch('/reset_app', {method:'POST'}); location.href = '/remote'; }
    fetch('/connect_phone', {method:'POST'}).then(() => upd());
</script></body></html>
"""

with open('templates/laptop.html', 'w', encoding='utf-8') as f: f.write(laptop_html)
with open('templates/remote.html', 'w', encoding='utf-8') as f: f.write(remote_html)

app = Flask(__name__)
INITIAL_STATE = {"connected": False, "mode": "plus", "problem": "", "size": 200, "color": "#d63384", "bg_color": "#fff5f8"}
state = INITIAL_STATE.copy()
session = {"start_time": 0, "problems": [], "answers": [], "filename": "", "results": {}}

@app.route('/')
def laptop_route(): return render_template('laptop.html')
@app.route('/remote')
def remote_route(): return render_template('remote.html')
@app.route('/get_state')
def get_state(): return jsonify(state)

@app.route('/connect_phone', methods=['POST'])
def connect(): state["connected"] = True; return "ok"

@app.route('/init_study', methods=['POST'])
def init_study():
    name = request.json.get('filename', 'Unnamed').replace(" ", "_")
    session["filename"] = f"{name}_{random.randint(1000, 9999)}.csv"
    session["results"] = {}
    return "ok"

@app.route('/gen_math', methods=['POST'])
def gen_math():
    session["start_time"] = time.time(); session["answers"] = []
    probs = [{"q": f"{random.randint(10,30)} {random.choice(['+','-'])} {random.randint(1,9)}"} for _ in range(10)]
    for p in probs:
        a, op, b = p['q'].split(); a, b = int(a), int(b)
        if op == '-' and a < b: p['q'] = f"{b} - {a}"
    session["problems"] = probs; state["mode"] = "math"; state["problem"] = probs[0]["q"]
    return jsonify(probs)

@app.route('/save', methods=['POST'])
def save():
    session["answers"].append(request.json.get('ans'))
    dur, test_num = round(time.time() - session["start_time"], 2), int(request.json.get('test_num'))
    score = sum(1 for i, p in enumerate(session["problems"]) if int(session["answers"][i]) == eval(p['q']))
    session["results"][f"Test {test_num} Accuracy"] = f"{score}/10"
    session["results"][f"Test {test_num} Duration (s)"] = dur
    if test_num == 2 and session["filename"]:
        pd.DataFrame([session["results"]]).to_csv(os.path.join(SAVE_DIR, session["filename"]), index=False)
    state["mode"] = "plus"; return "ok"

@app.route('/update_style', methods=['POST'])
def update_style(): state.update(request.json); return "ok"
@app.route('/set_mode', methods=['POST'])
def set_mode(): state["mode"] = request.json.get('mode'); return "ok"
@app.route('/upd_math', methods=['POST'])
def upd_math(): session["answers"].append(request.json.get('ans')); state["problem"] = request.json.get('prob'); return "ok"

@app.route('/reset_app', methods=['POST'])
def reset_app():
    global state, session
    state["mode"] = "reset_trigger" # Signal laptop to reload
    time.sleep(0.5)
    state = INITIAL_STATE.copy()
    session = {"start_time": 0, "problems": [], "answers": [], "filename": "", "results": {}}
    return "ok"

if __name__ == '__main__':
    webbrowser.open(BASE_URL)
    app.run(host='0.0.0.0', port=5000, debug=False)
