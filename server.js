const http = require('http');
const fs   = require('fs');
const WebSocket = require('ws');

const PORT       = 3000;
const R          = 5;          // sphere radius (world units)
const MOVE_SPD   = 0.025;      // radians/tick
const TURN_SPD   = 0.06;
const PROJ_SPD   = 0.05;
const PROJ_LIFE  = 120;        // ticks
const HIT_RAD    = 0.22;       // angular hit radius (radians)
const TICK_MS    = 50;         // 20 Hz

let players = {}, nextPid = 0;
let projs   = [], nextProjId = 0;

// ── Sphere math ───────────────────────────────────────────────────────────────

function sph2cart(th, ph) {
  return [Math.sin(ph)*Math.cos(th), Math.cos(ph), Math.sin(ph)*Math.sin(th)];
}

function dot([ax,ay,az],[bx,by,bz]) { return ax*bx+ay*by+az*bz; }

function angDist(t1,p1,t2,p2) {
  return Math.acos(Math.max(-1,Math.min(1, dot(sph2cart(t1,p1),sph2cart(t2,p2)))));
}

function move(th, ph, facing, dist) {
  const cp=Math.cos(ph),sp=Math.sin(ph),ct=Math.cos(th),st=Math.sin(th);
  const ef=[cp*ct,-sp,cp*st], et=[-st,0,ct];
  const cd=Math.cos(facing),sd=Math.sin(facing);
  const fw=[cd*ef[0]+sd*et[0], cd*ef[1]+sd*et[1], cd*ef[2]+sd*et[2]];
  const [px,py,pz]=sph2cart(th,ph);
  const c=Math.cos(dist),s=Math.sin(dist);
  let nx=px*c+fw[0]*s, ny=py*c+fw[1]*s, nz=pz*c+fw[2]*s;
  const m=Math.sqrt(nx*nx+ny*ny+nz*nz);
  nx/=m; ny/=m; nz/=m;
  return { th: Math.atan2(nz,nx), ph: Math.acos(Math.max(-1,Math.min(1,ny))) };
}

// ── Server ────────────────────────────────────────────────────────────────────

const server = http.createServer((req, res) => {
  fs.readFile(__dirname+'/game.html', (err, data) => {
    res.writeHead(err ? 404 : 200, {'Content-Type':'text/html'});
    res.end(err ? 'Not found' : data);
  });
});

const wss = new WebSocket.Server({ server });

function broadcast(msg) {
  const s = JSON.stringify(msg);
  wss.clients.forEach(c => c.readyState===WebSocket.OPEN && c.send(s));
}

wss.on('connection', ws => {
  const pid = nextPid++;
  players[pid] = {
    th: Math.random()*Math.PI*2,
    ph: 0.5 + Math.random()*(Math.PI-1),
    facing: 0, health: 3, score: 0
  };
  ws.send(JSON.stringify({ type:'welcome', pid }));

  ws.on('message', raw => {
    try {
      const msg = JSON.parse(raw);
      const p = players[pid]; if (!p) return;
      if (msg.type === 'input') {
        p.facing = (p.facing + (msg.turn||0)*TURN_SPD + Math.PI*2) % (Math.PI*2);
        if (msg.move) { const r=move(p.th,p.ph,p.facing,msg.move*MOVE_SPD); p.th=r.th; p.ph=r.ph; }
      } else if (msg.type === 'throw') {
        projs.push({ id:nextProjId++, owner:pid, th:p.th, ph:p.ph, facing:p.facing, age:0 });
      }
    } catch(_) {}
  });

  ws.on('close', () => delete players[pid]);
});

// ── Game loop ─────────────────────────────────────────────────────────────────

setInterval(() => {
  projs = projs.filter(p => {
    p.age++;
    if (p.age > PROJ_LIFE) return false;
    const r = move(p.th, p.ph, p.facing, PROJ_SPD);
    p.th = r.th; p.ph = r.ph;
    for (const [id, pl] of Object.entries(players)) {
      if (+id === p.owner) continue;
      if (angDist(p.th,p.ph,pl.th,pl.ph) < HIT_RAD) {
        if (--pl.health <= 0) {
          pl.health = 3;
          pl.th = Math.random()*Math.PI*2;
          pl.ph = 0.5+Math.random()*(Math.PI-1);
          if (players[p.owner]) players[p.owner].score++;
        }
        return false;
      }
    }
    return true;
  });
  broadcast({ type:'state', players, projs });
}, TICK_MS);

server.listen(PORT, () => console.log(`http://localhost:${PORT}`));
