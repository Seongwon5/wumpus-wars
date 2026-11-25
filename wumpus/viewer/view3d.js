// 3D 뷰 (three.js, MIT 라이선스). viewer.html 안에 <script type="module"> 로 끼워 넣는다.
// 리플레이 상태 (R, F, P, umap, ...) 는 viewer.html 본체의 전역 변수를 읽기만 한다.
// three.js 0.160 과 부가 모듈은 vendor/three.bundle.min.js 로 묶어 html 안에 넣는다 (replay.py). 인터넷이 필요 없다.
const {THREE, OrbitControls, RoundedBoxGeometry, EffectComposer, RenderPass, UnrealBloomPass, OutputPass} = window.__three;

const box = document.getElementById('three');
const renderer = new THREE.WebGLRenderer({antialias: true});
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
box.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0705);
scene.fog = new THREE.Fog(0x0b0705, 40, 90);
const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 400);
const controls = new OrbitControls(camera, renderer.domElement);
const PHI = 0.62;                      // 내려다보는 각도 (고정)
controls.enableDamping = true;
controls.enableRotate = false;
controls.minPolarAngle = controls.maxPolarAngle = PHI;
controls.minAzimuthAngle = controls.maxAzimuthAngle = 0;
controls.screenSpacePanning = false;   // 끌면 바닥을 따라 움직인다
controls.zoomToCursor = true;
controls.zoomSpeed = 2;
controls.mouseButtons = {LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN};
controls.touches = {ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_PAN};
controls.minDistance = 4;
controls.maxDistance = 90;

const hemi = new THREE.HemisphereLight(0xffe0b0, 0x1a1008, 0.42);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffd59a, 1.3);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.02;
scene.add(sun, sun.target);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.75, 0.5, 0.88);
composer.addPass(bloom);
composer.addPass(new OutputPass());

const TC = [{c: 0xff4a3a, d: 0x9a2216, l: 0xffc2b0, css: '#ff4a3a'}, {c: 0x2ec4ff, d: 0x125f86, l: 0xbfeaf5, css: '#2ec4ff'}];
const MINDHEX = {green: 0x50dc78, red: 0xff4646, yellow: 0xffc83c, blue: 0x50a0ff, purple: 0xb46eff, white: 0xffffff};
const CH = 1.5;                       // 캐릭터 크기
const std = (c, o = {}) => new THREE.MeshStandardMaterial(Object.assign({color: c, roughness: 0.7, metalness: 0.05}, o));
const wx = x => x - W / 2 + 0.5, wz = y => y - H / 2 + 0.5;
const easeOut = t => 1 - Math.pow(1 - t, 3);
const elastic = t => t <= 0 ? 0 : t >= 1 ? 1 : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * 2.094) + 1;
const lerpAng = (a, b, k) => { const d = ((b - a + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI; return a + d * k; };
const HITC = new THREE.Color(0.9, 0.08, 0.08);
const M4 = new THREE.Matrix4(), COL = new THREE.Color(), Q = new THREE.Quaternion(), V3 = new THREE.Vector3(), S3 = new THREE.Vector3();

let world = null;
let evCache = new Map();

function mesh(parent, geo, mat, x = 0, y = 0, z = 0, shadow = true) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  m.castShadow = shadow;
  parent.add(m);
  return m;
}

function hpBar(w) {
  const g = new THREE.Group();
  const bg = new THREE.Mesh(new THREE.PlaneGeometry(w + 0.04, 0.1), new THREE.MeshBasicMaterial({color: 0x000000, transparent: true, opacity: 0.6, depthTest: false}));
  const fill = new THREE.Mesh(new THREE.PlaneGeometry(w, 0.065), new THREE.MeshBasicMaterial({color: 0xffffff, depthTest: false}));
  bg.renderOrder = 10; fill.renderOrder = 11; fill.position.z = 0.001;
  g.add(bg, fill);
  g.userData = {w, fill};
  return g;
}
function setHp(bar, frac, teamCol) {
  frac = Math.max(0, Math.min(1, frac));
  const {w, fill} = bar.userData;
  fill.scale.x = Math.max(0.001, frac);
  fill.position.x = -(1 - frac) * w / 2;
  fill.material.color.setHex(frac > 0.5 ? teamCol : frac > 0.25 ? 0xffb84d : 0xff4d4d);
}
function billboard(obj, parent) {   // 부모가 돌아 있어도 카메라를 보게
  parent.getWorldQuaternion(Q).invert().multiply(camera.quaternion);
  obj.quaternion.copy(Q);
}

let _star = null, _hole = null, _shaft = null, _soft = null, _slab = null, _brick = null;
function rnd(seed) { let t = seed >>> 0; return () => { t += 0x6D2B79F5; let r = Math.imul(t ^ (t >>> 15), 1 | t); r ^= r + Math.imul(r ^ (r >>> 7), 61 | r); return ((r ^ (r >>> 14)) >>> 0) / 4294967296; }; }
function speckle(g, w, h, R, n, lo, hi) {          // 돌 표면의 얼룩과 알갱이
  for (let i = 0; i < n; i++) {
    const v = lo + R() * (hi - lo), s = 1 + R() * 3;
    g.fillStyle = `rgba(${v},${v * 0.86},${v * 0.66},${0.08 + R() * 0.14})`;
    g.fillRect(R() * w, R() * h, s, s);
  }
}
function slabTex() {                                 // 바닥 판석: 닳은 모서리, 금, 얼룩
  if (_slab) return _slab;
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), R = rnd(7);
  g.fillStyle = '#9c8466'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 18; i++) {                     // 큰 얼룩
    const x = R() * 256, y = R() * 256, r = 30 + R() * 70, gr = g.createRadialGradient(x, y, 0, x, y, r);
    const d = R() < 0.5 ? '70,52,34' : '196,170,130';
    gr.addColorStop(0, `rgba(${d},${0.10 + R() * 0.12})`); gr.addColorStop(1, `rgba(${d},0)`);
    g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  }
  speckle(g, 256, 256, R, 2600, 60, 220);
  g.strokeStyle = 'rgba(40,28,16,0.55)'; g.lineWidth = 1.6;          // 금
  for (let k = 0; k < 3; k++) {
    let x = R() * 256, y = R() * 256; g.beginPath(); g.moveTo(x, y);
    for (let i = 0; i < 6; i++) { x += (R() - 0.5) * 60; y += (R() - 0.3) * 40; g.lineTo(x, y); }
    g.stroke();
  }
  const e = g.createLinearGradient(0, 0, 256, 256);                   // 닳은 모서리 (빛 · 그늘)
  g.lineWidth = 14; g.strokeStyle = 'rgba(30,20,10,0.35)'; g.strokeRect(0, 0, 256, 256);
  g.lineWidth = 4; g.strokeStyle = 'rgba(255,230,190,0.18)'; g.strokeRect(9, 9, 238, 238);
  _slab = new THREE.CanvasTexture(c); _slab.colorSpace = THREE.SRGBColorSpace; _slab.anisotropy = 8;
  return _slab;
}
function brickTex() {                                // 석벽: 엇갈려 쌓은 돌과 줄눈
  if (_brick) return _brick;
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), R = rnd(11);
  g.fillStyle = '#3a2c1e'; g.fillRect(0, 0, 256, 256);               // 줄눈
  const rowsN = 4, rh = 256 / rowsN;
  for (let r = 0; r < rowsN; r++) {
    let x = r % 2 ? -40 : 0;
    while (x < 256) {
      const w = 70 + R() * 50, v = 120 + R() * 50;
      g.fillStyle = `rgb(${v},${v * 0.83},${v * 0.62})`;
      g.fillRect(x + 3, r * rh + 3, w - 6, rh - 6);
      const gr = g.createLinearGradient(0, r * rh, 0, r * rh + rh);
      gr.addColorStop(0, 'rgba(255,235,200,0.16)'); gr.addColorStop(1, 'rgba(0,0,0,0.28)');
      g.fillStyle = gr; g.fillRect(x + 3, r * rh + 3, w - 6, rh - 6);
      x += w;
    }
  }
  speckle(g, 256, 256, R, 3000, 50, 210);
  _brick = new THREE.CanvasTexture(c); _brick.colorSpace = THREE.SRGBColorSpace; _brick.anisotropy = 8;
  return _brick;
}
function shaftTex() {
  if (_shaft) return _shaft;
  const c = document.createElement('canvas'); c.width = 64; c.height = 256;
  const g = c.getContext('2d'), gr = g.createLinearGradient(0, 0, 0, 256);
  gr.addColorStop(0, '#4a3826'); gr.addColorStop(0.12, '#2c2015'); gr.addColorStop(0.45, '#0b0704'); gr.addColorStop(1, '#000');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 256);
  g.strokeStyle = 'rgba(0,0,0,0.5)'; g.lineWidth = 2;
  for (let y = 10; y < 120; y += 22) { g.beginPath(); g.moveTo(0, y); g.lineTo(64, y + 3); g.stroke(); }
  _shaft = new THREE.CanvasTexture(c); _shaft.colorSpace = THREE.SRGBColorSpace;
  return _shaft;
}
function softTex() {
  if (_soft) return _soft;
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,0.9)'); gr.addColorStop(0.5, 'rgba(255,255,255,0.25)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
  _soft = new THREE.CanvasTexture(c);
  return _soft;
}
const _badge = new Map(), _num = new Map();
function numTex(n) {                 // 금맥에 남은 양: 금빛 테두리 이름표
  if (_num.has(n)) return _num.get(n);
  const c = document.createElement('canvas'); c.width = 128; c.height = 64;
  const g = c.getContext('2d');
  g.beginPath(); g.roundRect(6, 8, 116, 50, 16); g.fillStyle = 'rgba(14,9,5,0.55)'; g.fill();
  g.lineWidth = 2.5; g.strokeStyle = 'rgba(217,164,65,0.45)'; g.stroke();
  g.fillStyle = '#ecd29a'; g.font = '700 46px Cinzel, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(String(n), 64, 36);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  _num.set(n, t);
  return t;
}
function badgeTex(kind, team, carry = 0, hp10 = 10, arrows = -1) {
  const key = kind + team + ':' + carry + ':' + hp10 + ':' + arrows;
  if (_badge.has(key)) return _badge.get(key);
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), col = TC[team].css;
  const shape = (r) => {
    g.beginPath();
    if (kind === 'G') { for (let i = 0; i < 6; i++) { const t = i / 6 * Math.PI * 2 + Math.PI / 6; g.lineTo(128 + Math.cos(t) * r, 128 + Math.sin(t) * r); } g.closePath(); }
    else g.arc(128, 128, r, 0, 7);
  };
  shape(122); g.fillStyle = '#0b0705'; g.fill();               // 바깥 검은 테
  shape(112); g.fillStyle = '#4a3b2c'; g.fill();               // 비어 있는 체력 (어두운 고리)
  g.save(); shape(112); g.clip();                              // 남은 체력만큼 팀 색으로 (12시부터 시계 방향)
  g.beginPath(); g.moveTo(128, 128); g.arc(128, 128, 140, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * hp10 / 10); g.closePath();
  g.fillStyle = hp10 <= 3 ? '#ff6a3d' : col; g.fill(); g.restore();
  shape(84); g.fillStyle = '#1a110a'; g.fill();                // 어두운 바탕
  g.fillStyle = '#ffffff'; g.strokeStyle = '#ffffff'; g.lineCap = 'round'; g.lineJoin = 'round';
  if (kind === 'G') {          // 활: 굵은 활대 + 시위 + 화살
    g.lineWidth = 20; g.beginPath(); g.arc(98, 128, 62, -1.2, 1.2); g.stroke();
    const ax = 98 + Math.cos(1.2) * 62, ay = 62 * Math.sin(1.2);
    g.lineWidth = 6; g.beginPath(); g.moveTo(ax, 128 - ay); g.lineTo(ax, 128 + ay); g.stroke();
    g.lineWidth = 12; g.beginPath(); g.moveTo(70, 128); g.lineTo(170, 128); g.stroke();
    g.beginPath(); g.moveTo(196, 128); g.lineTo(160, 104); g.lineTo(160, 152); g.closePath(); g.fill();
    g.lineWidth = 8; g.beginPath(); g.moveTo(70, 128); g.lineTo(56, 112); g.moveTo(70, 128); g.lineTo(56, 144); g.stroke();
  } else {                     // 곡괭이: 대각선 자루 + 양 끝이 뾰족한 머리
    g.lineWidth = 22; g.beginPath(); g.moveTo(84, 190); g.lineTo(146, 118); g.stroke();
    g.save(); g.translate(146, 118); g.rotate(Math.atan2(-72, 62) + Math.PI / 2);   // 자루와 직각, 볼록한 쪽이 바깥
    g.beginPath();                                // 양 끝이 뾰족한 두꺼운 초승달 머리
    g.moveTo(-92, 34); g.quadraticCurveTo(-46, -46, 0, -44); g.quadraticCurveTo(46, -46, 92, 34);
    g.quadraticCurveTo(40, -6, 0, -6); g.quadraticCurveTo(-40, -6, -92, 34); g.closePath(); g.fill();
    g.fillRect(-16, -30, 32, 34);                 // 자루를 끼우는 쇠
    g.restore();
  }
  if (carry > 0) {             // 든 금: 오른쪽 아래 금화에 숫자
    g.beginPath(); g.arc(186, 186, 70, 0, 7); g.fillStyle = '#0b0705'; g.fill();
    g.beginPath(); g.arc(186, 186, 61, 0, 7); g.fillStyle = '#f2b52e'; g.fill();
    g.lineWidth = 6; g.strokeStyle = '#fff1b0'; g.stroke();
    g.fillStyle = '#2a1600'; g.font = '800 92px Cinzel, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(String(carry), 186, 192);
  }
  if (arrows >= 0) {           // 남은 화살: 왼쪽 아래 화살 표지에 숫자 (0 이면 붉게)
    g.beginPath(); g.arc(70, 186, 64, 0, 7); g.fillStyle = '#0b0705'; g.fill();
    g.beginPath(); g.arc(70, 186, 55, 0, 7); g.fillStyle = arrows ? '#dfeeff' : '#ff6a3d'; g.fill();
    g.strokeStyle = '#1a2230'; g.lineWidth = 7; g.beginPath(); g.moveTo(38, 214); g.lineTo(62, 190); g.stroke();
    g.fillStyle = '#1a2230'; g.font = '800 84px Cinzel, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(String(arrows), 80, 192);
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  _badge.set(key, t);
  return t;
}
// 도트 초상 (20×20). 글자 하나가 픽셀 하나, '.' 은 비움. 'b' 'n' 'q' 는 팀 색.
const PIX = {
  E: ['....................', '........hhhh........', '.......hhhhhh.......', '......hhhhhhhh......', '......bbbbbbbb......',
      '...hhhhhhhhhhhhhh...', '....HHHHHHHHHHHH....', '......rssssssr......', '......sesssses......', '......ssssSsss......',
      '.....Ssssssssss.....', '......tsmmmmst......', '......tttttttt......', '.......tsssst.......', '.....nnnnssnnnn.....',
      '...vvvcnnnnnncvvv...', '..vvvvccnnnnccvvvv..', '..vvvvcccnncccvvvv..', '.vvvvvccccccccvvvvv.', '.vvvvvccccccccvvvvv.'],
  G: ['....................', '........yyyy........', '......yyyyyyyy......', '.....yyyyyyyyyy.yy..', '....yyYyyyyyyYyyyyy.',
      '....yYssssssssYyyy..', '....yssssssssssyYy..', '....ylelsssslelyYy..', '....yksssSssskyyYy..', '....yssssppssssyYy..',
      '.....ysssssssy.yYy..', '......yssssssy..yy..', '.......qssssq....y..', '.....qqqqccqqqq.....', '...qqqvvccccvvqqq...',
      '..qqqvvvccccvvvqqq..', '..qqqvvvccccvvvqqq..', '.qqqqvvvccccvvvqqqq.', '.qqqqvvvccccvvvqqqq.', '.qqqqvvvccccvvvqqqq.'],
  W: ['....................', '..o..............o..', '..oo............oo..', '...oo..GGGGGG..oo...', '....oGGggggggGGo....',
      '....GggggggggggG....', '...GgkeeggggeekgG...', '...GggggggggggggG...', '..GgggmmmmmmmmgggG..', '..GggmttttttttmggG..',
      '..GggmmmmmmmmmmggG..', '..GgggmttttttmgggG..', '..GggggggggggggggG..', '.GggBBBBBBBBBBBBggG.', '.GgBBBBBBBBBBBBBBgG.',
      'GgGBBBBBBBBBBBBBBGgG', 'GgGBBBBBBBBBBBBBBGgG', 'ggGBBBBBBBBBBBBBBGgg', 'ggGGBBBBBBBBBBBBGGgg', 'gggGGGGGGGGGGGGGGggg'],
};
const PAL = {h: '#6b4423', H: '#3e2512', r: '#3b2414', s: '#e0a97e', S: '#b57f5a', e: '#15120e', t: '#8a6a50', m: '#7a3a2a',
  c: '#e8dcc4', v: '#7a4c26', y: '#e9b452', Y: '#a8742a', l: '#2a1a10', k: '#f2a0a0', p: '#c84a5a',
  g: '#6f9a34', G: '#3c5a1c', B: '#b6a862', o: '#b8ae90', M: '#5a1410', t2: '#e4dcc2'};
function drawPix(g, key, team, x0, y0, px) {
  const rows = PIX[key], col = team >= 0 ? TC[team].css : '#8fff3a', dark = team >= 0 ? '#' + TC[team].d.toString(16).padStart(6, '0') : '#2a3a10';
  for (let y = 0; y < 20; y++) for (let x = 0; x < 20; x++) {
    const ch = (rows[y] || '')[x] || '.';
    if (ch === '.') continue;
    let c = PAL[ch];
    if (ch === 'b' || ch === 'n' || ch === 'q') c = (ch === 'q' && (x + y) % 5 === 0) ? dark : col;
    if (key === 'W') { if (ch === 'e') c = '#e8ff50'; else if (ch === 'k') c = '#140e08'; else if (ch === 't') c = '#bdb39a'; else if (ch === 'm') c = '#5a1410'; }
    if (key === 'G' && ch === 'e') c = '#2e8a52';
    g.fillStyle = c; g.fillRect(x0 + x * px, y0 + y * px, px, px);
  }
}
const _tok = new Map();
function tokenTex(kind, team, carry = 0, hp10 = 10, arrows = -1) {   // 둥근 패: 팀 색 고리 (= 체력) 안에 도트 초상
  const key = kind + team + ':' + carry + ':' + hp10 + ':' + arrows;
  if (_tok.has(key)) return _tok.get(key);
  const N = 160, c = document.createElement('canvas'); c.width = c.height = N;
  const g = c.getContext('2d'), col = team >= 0 ? TC[team].css : '#8fff3a';
  g.imageSmoothingEnabled = false;
  const disc = (r, f) => { g.beginPath(); g.arc(80, 80, r, 0, 7); g.fillStyle = f; g.fill(); };
  disc(79, '#0b0705');
  disc(74, '#3a2e22');
  g.save(); g.beginPath(); g.arc(80, 80, 74, 0, 7); g.clip();
  g.beginPath(); g.moveTo(80, 80); g.arc(80, 80, 90, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * hp10 / 10); g.closePath();
  g.fillStyle = hp10 <= 3 ? '#ff6a3d' : col; g.fill(); g.restore();
  disc(63, '#0b0705');
  const gr = g.createRadialGradient(80, 70, 6, 80, 80, 62);
  gr.addColorStop(0, '#5c4a36'); gr.addColorStop(1, '#1c140c');
  disc(60, gr);
  g.save(); g.beginPath(); g.arc(80, 80, 60, 0, 7); g.clip();
  const nmT = sheetName(kind, team), ST = nmT && SHEETS[nmT];
  const PT = kind === 'E' && team >= 0 && SHEETS['portrait_' + team];
  if (PT) { g.fillStyle = team ? '#0e1a2c' : '#2a100c'; g.fillRect(0, 0, N, N); g.drawImage(PT.img, 0, 0, 64, 64, 18, 18, 124, 124); }   // 초상화 (64px) 를 원에 꽉 차게
  else if (ST) { const C = SP.meta.cell, r = ST.m.idle.row + 2;                  // LPC 얼굴: 머리만 바짝 잘라 원을 꽉 채운다
    if (kind === 'W') g.drawImage(ST.img, 32 + 14, r * C + 32 + 2, 36, 36, 12, 14, 136, 136);
    else g.drawImage(ST.img, 32 + 18, r * C + 32 + 10, 28, 28, 16, 16, 128, 128); }   // 상반신 초상: 얼굴 전체 + 어깨 (버섯처럼 보이지 않게)
  else { const bc = bodyCanvas(kind, team, 0);          // 서 있는 도트 캐릭터의 얼굴 부분을 크게
    if (kind === 'W') g.drawImage(bc, 2, 0, 36, 36, 20, 22, 120, 120); else g.drawImage(bc, 8, 2, 17, 17, 20, 22, 120, 120); }
  g.restore();
  const chip = (cx, cy, fill, txt, ink) => {
    g.beginPath(); g.arc(cx, cy, 25, 0, 7); g.fillStyle = '#0b0705'; g.fill();
    g.beginPath(); g.arc(cx, cy, 20, 0, 7); g.fillStyle = fill; g.fill();
    g.fillStyle = ink; g.font = '800 30px Cinzel, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(txt, cx, cy + 2);
  };
  if (arrows >= 0) chip(30, 130, arrows ? '#dfeeff' : '#ff6a3d', arrows ? '➶' + arrows : '🗡', '#1a2230');
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  t.magFilter = THREE.NearestFilter; t.anisotropy = 4;
  _tok.set(key, t);
  return t;
}
// ---------------- 도트 그림 도구 ----------------
const HEXC = new Map();
function rgbOf(c) { if (Array.isArray(c)) return c; let v = HEXC.get(c); if (!v) { const n = parseInt(c.slice(1), 16); v = [n >> 16 & 255, n >> 8 & 255, n & 255]; HEXC.set(c, v); } return v; }
function shade(c, k) { const [r, g, b] = rgbOf(c); return (k >= 0 ? [r + (255 - r) * k, g + (255 - g) * k, b + (255 - b) * k] : [r * (1 + k), g * (1 + k), b * (1 + k)]).map(v => Math.max(0, Math.min(255, Math.round(v)))); }
function teamHex(team, which) { return '#' + TC[team][which].toString(16).padStart(6, '0'); }
function pxCanvas(w, h, draw, seed = 1) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d'), img = ctx.createImageData(w, h), D = img.data, rn = rnd(seed);
  const K = {
    w, h, rn,
    P(x, y, col) { x = Math.floor(x); y = Math.floor(y); if (!col || x < 0 || y < 0 || x >= w || y >= h) return; const v = rgbOf(col), i = (y * w + x) * 4; D[i] = v[0]; D[i + 1] = v[1]; D[i + 2] = v[2]; D[i + 3] = 255; },
    R(x, y, ww, hh, col) { for (let j = 0; j < hh; j++) for (let i = 0; i < ww; i++) K.P(x + i, y + j, col); },
    E(cx, cy, rx, ry, col, fn) {
      for (let y = Math.floor(cy - ry - 1); y <= cy + ry + 1; y++) for (let x = Math.floor(cx - rx - 1); x <= cx + rx + 1; x++) {
        const dx = (x + 0.5 - cx) / rx, dy = (y + 0.5 - cy) / ry;
        if (dx * dx + dy * dy <= 1) K.P(x, y, fn ? fn(x, y, dx, dy) : col);
      }
    },
    L(x0, y0, x1, y1, col, t = 1) {
      const n = Math.ceil(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) * 2) + 1;
      for (let i = 0; i <= n; i++) { const x = x0 + (x1 - x0) * i / n, y = y0 + (y1 - y0) * i / n; K.R(Math.round(x - (t - 1) / 2), Math.round(y - (t - 1) / 2), t, t, col); }
    },
    A(x, y) { if (x < 0 || y < 0 || x >= w || y >= h) return 0; return D[(y * w + x) * 4 + 3]; },
    C(x, y) { const i = (y * w + x) * 4; return [D[i], D[i + 1], D[i + 2]]; },
    clear(x, y) { if (x >= 0 && y >= 0 && x < w && y < h) D[(y * w + x) * 4 + 3] = 0; },
    noise(x, y, ww, hh, base, amp) { for (let j = 0; j < hh; j++) for (let i = 0; i < ww; i++) { const d = Math.round((rn() - 0.5) * 2 * amp); K.P(x + i, y + j, rgbOf(base).map(v => Math.max(0, Math.min(255, v + d)))); } },
    outline(col) {
      const a = new Uint8Array(w * h); for (let i = 0; i < w * h; i++) a[i] = D[i * 4 + 3];
      const on = (x, y) => x >= 0 && y >= 0 && x < w && y < h && a[y * w + x];
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (!a[y * w + x] && (on(x - 1, y) || on(x + 1, y) || on(x, y - 1) || on(x, y + 1))) K.P(x, y, col);
    },
  };
  draw(K);
  ctx.putImageData(img, 0, 0);
  return c;
}
function pxTex(c, mip = false) {
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.magFilter = THREE.NearestFilter;
  if (mip) { t.minFilter = THREE.LinearMipmapLinearFilter; t.anisotropy = 8; } else { t.minFilter = THREE.NearestFilter; t.generateMipmaps = false; }
  return t;
}
const _pxc = new Map();
function pxMemo(key, make) { let v = _pxc.get(key); if (!v) { v = make(); _pxc.set(key, v); } return v; }
function pxSprite(tex, w, h, cy = 0.04) {
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: tex, transparent: true, alphaTest: 0.5}));
  sp.center.set(0.5, cy); sp.scale.set(w, h, 1); sp.renderOrder = 5;
  return sp;
}

// ---------------- 도트 캐릭터 (32×48) ----------------
function drawExplorer(K, team, fr) {          // 머리가 키의 1/3 쯤인 날씬한 비율 (32×48 안에 키 약 42)
  const T = teamHex(team, 'c'), Td = teamHex(team, 'd');
  const pants = '#4a3a2a', pantsD = '#33271b', boot = '#2a1a10', bootL = '#55361e';
  const shirt = '#d8ccb0', shirtD = '#b0a080', vest = '#7a4c26', vestD = '#54301a', vestL = '#9a6438';
  const skin = '#e0ac84', skinD = '#bc8660', hair = '#3b2414', hat = '#6b4423', hatD = '#45291a', hatL = '#8c5c32';
  const iron = '#9aa4b0', ironL = '#d8dee6', ironD = '#5a6270', wood = '#8a5a2a', woodL = '#b07a40';
  const up = fr === 1 ? [2, 0] : fr === 2 ? [0, 2] : [0, 0], sp = fr ? 1 : 0;
  // 다리 · 장화
  [[13 - sp, up[0], pants], [17 + sp, up[1], pantsD]].forEach(([x, u, c], i) => {
    K.R(x, 30, 3, 10 - u, c); K.R(x + (i ? 2 : 0), 30, 1, 10 - u, i ? shade(pantsD, -0.2) : shade(pants, 0.15));
    K.R(x - (i ? 0 : 1), 40 - u, 4, 4, boot); K.R(x - (i ? 0 : 1), 40 - u, 4, 1, bootL); K.R(x - (i ? 0 : 1), 43 - u, 4, 1, '#140a04');
  });
  // 몸통
  K.R(12, 18, 9, 11, shirt); K.R(12, 18, 2, 11, vest); K.R(19, 18, 2, 11, vestD); K.P(12, 18, vestL); K.R(12, 19, 1, 9, vestL);
  K.R(17, 19, 1, 8, shirtD); K.P(16, 21, shirtD); K.P(16, 24, shirtD);
  K.R(12, 28, 9, 2, '#3a2414'); K.R(15, 28, 2, 2, '#ffc63a');
  K.L(13, 18, 20, 27, '#5a3418');                                         // 가방 끈 · 가방
  K.R(19, 26, 4, 4, '#8a5a2a'); K.R(19, 26, 4, 1, '#a87040'); K.P(20, 28, '#ffc63a');
  const sw = fr === 1 ? 1 : fr === 2 ? -1 : 0;
  K.R(10, 18 + sw, 2, 8, shirt); K.R(10, 18 + sw, 1, 8, shirtD); K.R(10, 26 + sw, 2, 2, skin);   // 왼팔
  // 곡괭이
  K.L(22, 32, 24, 4, wood, 1); K.L(23, 32, 25, 4, woodL, 1);
  K.L(24, 4, 20, 5, iron, 2); K.L(20, 5, 18, 8, iron, 1); K.L(24, 4, 27, 5, iron, 2); K.L(27, 5, 28, 8, iron, 1);
  K.L(20, 4, 26, 3, ironL, 1); K.R(23, 3, 2, 2, ironD);
  K.R(21, 18, 2, 5, shirt); K.R(22, 18, 1, 5, shirtD); K.R(21, 22, 3, 2, skin);                // 오른팔 · 쥔 손
  // 목 · 목수건
  K.R(15, 16, 3, 2, skinD); K.R(13, 17, 7, 1, T); K.R(15, 18, 3, 1, Td);
  // 얼굴
  K.E(16.5, 12.5, 3.6, 4, skin, (x, y, dx, dy) => dx > 0.5 || dy > 0.6 ? skinD : skin);
  K.P(12, 12, skinD); K.P(20, 12, skinD);
  K.R(13, 9, 1, 4, hair); K.R(19, 9, 1, 4, hair);
  K.P(15, 11, hair); K.P(18, 11, hair);
  K.P(15, 12, '#1a120a'); K.P(18, 12, '#1a120a');
  K.P(17, 13, skinD);
  K.R(16, 15, 2, 1, '#8a3a2a'); K.P(14, 14, '#a88262'); K.P(19, 14, '#a88262'); K.P(15, 16, '#a88262');
  // 중절모
  K.E(16.5, 9, 7, 1.5, hat, (x, y, dx, dy) => dy < -0.2 ? hatL : hatD);
  K.R(13, 4, 7, 5, hat); K.clear(13, 4); K.clear(19, 4);
  K.R(13, 5, 1, 3, hatL); K.R(18, 5, 2, 3, hatD); K.R(15, 4, 3, 1, hatD);
  K.R(13, 7, 7, 1, T);
  K.outline('#140c06');
}

function drawArcher(K, team, fr) {
  const T = teamHex(team, 'c'), Td = teamHex(team, 'd');
  const skin = '#ecc4a6', skinD = '#cc9c80', hair = '#e8b850', hairL = '#f8d880', hairD = '#a87228';
  const blouse = '#ddd2ba', blouseD = '#b8ac90', cors = '#6a3c1c', corsL = '#8a5430', boot = '#3a2414', bootL = '#5e3c22', wood = '#8a5a2a', woodL = '#c08a48';
  // 망토 (뒤)
  for (let y = 17; y <= 38; y++) { const half = 4 + (y - 17) / 21 * 3.5, x0 = Math.round(16.5 - half), x1 = Math.round(16.5 + half); K.R(x0, y, x1 - x0 + 1, 1, y > 36 ? Td : T); K.P(x0, y, Td); K.P(x1, y, Td); }
  // 화살통
  K.R(20, 9, 3, 11, '#6a4020'); K.R(20, 9, 1, 11, '#8a5430'); K.R(20, 12, 3, 1, '#ffc63a');
  K.R(20, 6, 1, 3, '#e8e2d0'); K.R(22, 5, 1, 4, T);
  // 다리 · 장화
  const up = fr === 1 ? [2, 0] : fr === 2 ? [0, 2] : [0, 0], sp = fr ? 1 : 0;
  [[14 - sp, up[0]], [17 + sp, up[1]]].forEach(([x, u], i) => {
    K.R(x, 33, 2, 6 - u, '#3a2a36');
    K.R(x - (i ? 0 : 1), 38 - u, 3, 6, boot); K.R(x - (i ? 0 : 1), 38 - u, 3, 1, bootL); K.R(x - (i ? 0 : 1), 43 - u, 3, 1, '#140a04');
  });
  // 치마
  for (let y = 26; y <= 33; y++) { const half = 4 + (y - 26) * 0.45, x0 = Math.round(16.5 - half); K.R(x0, y, Math.round(half * 2) + 1, 1, y === 33 ? Td : T); }
  K.L(15, 28, 14, 33, Td); K.L(18, 28, 19, 33, Td);
  // 몸통
  K.R(13, 17, 7, 9, blouse); K.R(18, 17, 2, 9, blouseD);
  K.R(14, 21, 5, 5, cors); K.R(14, 21, 1, 5, corsL); K.P(16, 22, '#ffc63a'); K.P(16, 24, '#ffc63a');
  // 팔
  const sw = fr === 1 ? 1 : fr === 2 ? -1 : 0;
  K.R(11, 17, 2, 8, blouse); K.R(11, 17, 1, 8, blouseD);
  K.R(20, 17 - sw, 2, 8, blouse); K.R(21, 17 - sw, 1, 8, blouseD); K.R(20, 25 - sw, 2, 2, skin);
  // 활
  for (let y = 8; y <= 40; y++) { const t = (y - 8) / 32, x = Math.round(9 - Math.sin(Math.PI * t) * 4); K.P(x, y, t < 0.06 || t > 0.94 ? '#e0c070' : wood); K.P(x + 1, y, t < 0.06 || t > 0.94 ? '#e0c070' : woodL); }
  K.L(10, 9, 10, 39, '#d8d2c0');
  K.R(10, 24, 2, 2, skin);
  // 머리카락 · 꽁지머리
  K.R(15, 15, 3, 2, skinD);
  K.E(16.5, 9.5, 4.6, 4.3, hair);
  K.E(21.5, 9, 1.8, 2.5, hair); K.E(22, 13.5, 1.4, 3.2, hair, (x, y, dx) => dx > 0.2 ? hairD : hair);
  K.P(20, 7, T);
  K.R(12, 9, 1, 6, hair); K.R(20, 9, 1, 5, hair); K.P(12, 14, hairD);
  // 얼굴
  K.E(16.5, 11.8, 3.4, 3.8, skin, (x, y, dx, dy) => dx > 0.5 || dy > 0.65 ? skinD : skin);
  K.R(13, 6, 7, 3, hair); K.P(13, 9, hair); K.P(19, 9, hair); K.P(18, 9, hair);
  K.R(14, 6, 3, 1, hairL); K.P(14, 7, hairL);
  K.P(15, 10, '#2a1a10'); K.P(18, 10, '#2a1a10');
  K.R(15, 11, 1, 2, '#2e8a52'); K.R(18, 11, 1, 2, '#2e8a52');
  K.P(14, 13, '#e89a9a'); K.P(19, 13, '#e89a9a');
  K.R(16, 14, 2, 1, '#c84a5a');
  K.outline('#140c06');
}

function drawWumpus(K, dead) {
  const bone = '#e4dcc2', boneD = '#a89e82';
  if (dead) {                                     // 해골과 갈비뼈
    for (let k = 0; k < 5; k++) { K.L(8 + k * 5, 37, 10 + k * 5, 30, '#d8d0b6', 2); K.P(10 + k * 5, 30, boneD); }
    K.L(6, 34, 36, 34, boneD, 2);
    K.E(21, 26, 8, 6.5, bone, (x, y, dx, dy) => dy > 0.4 ? boneD : bone);
    K.L(14, 22, 7, 13, bone, 3); K.L(28, 22, 35, 13, bone, 3);
    K.E(18, 26, 1.8, 1.8, '#140e08'); K.E(24.5, 26, 1.8, 1.8, '#140e08');
    for (const x of [16, 19, 22, 25]) K.R(x, 31, 2, 2, bone);
    K.outline('#1a1408');
    return;
  }
  const fur = '#5f8a2e', furD = '#3c5a1c', furL = '#86b04a', belly = '#c2b46a', bellyD = '#9a8c4c';
  K.E(6, 30, 4, 6, furD); K.E(34, 30, 4, 6, furD);                                   // 팔 (뒤)
  for (let i = 0; i < 3; i++) { K.P(3 + i * 2, 36, bone); K.P(32 + i * 2, 36, bone); }
  K.E(20, 25, 14, 13, fur, (x, y, dx, dy) => { const s = dx * 0.6 + dy * 0.8; return s > 0.55 ? furD : s < -0.5 ? furL : (K.rn() < 0.08 ? furD : fur); });
  K.E(12, 38, 5, 2, furD); K.E(28, 38, 5, 2, furD);                                   // 발
  for (const x of [9, 11, 13, 25, 27, 29]) K.P(x, 39, bone);
  K.E(20, 30, 8.5, 7, belly, (x, y, dx, dy) => (y % 3 === 0 ? bellyD : dy > 0.55 ? bellyD : belly));
  K.L(10, 15, 5, 4, bone, 3); K.L(5, 4, 3, 1, bone, 2); K.L(30, 15, 35, 4, bone, 3); K.L(35, 4, 37, 1, bone, 2);   // 뿔
  K.L(11, 15, 6, 5, boneD, 1); K.L(31, 15, 36, 5, boneD, 1);
  K.R(10, 16, 8, 2, furD); K.R(23, 16, 8, 2, furD);                                   // 눈썹
  K.E(14, 19.5, 3, 2, '#e8ff50'); K.E(26, 19.5, 3, 2, '#e8ff50'); K.R(14, 18, 1, 3, '#140e08'); K.R(26, 18, 1, 3, '#140e08');
  K.R(11, 23, 19, 5, '#3a0a08'); K.R(12, 24, 17, 3, '#6a1810');                        // 입과 이빨
  for (const x of [12, 15, 18, 21, 24, 27]) { K.R(x, 23, 2, 1, bone); K.P(x, 24, bone); }
  for (const x of [13, 17, 22, 26]) { K.R(x, 27, 2, 1, bone); K.P(x, 26, bone); }
  K.outline('#0e1408');
}

function bodyCanvas(kind, team, fr) {
  return pxMemo('bc' + kind + team + ':' + fr, () => kind === 'W' ? pxCanvas(40, 40, K => drawWumpus(K, fr === 9), 5)
    : pxCanvas(32, 48, K => kind === 'G' ? drawArcher(K, team, fr) : drawExplorer(K, team, fr), 3));
}
function bodyTex(kind, team, fr) { return pxMemo('bt' + kind + team + ':' + fr, () => pxTex(bodyCanvas(kind, team, fr))); }

// ---------------- 도트 게임판 ----------------
function tileTex(name) {                     // LPC 동굴 타일 (있으면): 가까이선 도트 그대로, 멀리선 부드럽게
  const S = typeof SHEETS !== 'undefined' && SHEETS[name];
  if (!S) return null;
  return pxMemo('lpc_' + name, () => { const t = new THREE.Texture(S.img); t.colorSpace = THREE.SRGBColorSpace; t.magFilter = THREE.NearestFilter;
    t.minFilter = THREE.LinearMipmapLinearFilter; t.anisotropy = 8; t.needsUpdate = true; return t; });
}
function floorTex() {                       // 바닥 판석: 네 조각 돌, 줄눈, 금, 자갈 (칸마다 색은 인스턴스 색으로)
  const lt = tileTex('floor'); if (lt) return lt;
  return pxMemo('floor', () => pxTex(pxCanvas(32, 32, K => {
    K.noise(0, 0, 32, 32, [200, 194, 184], 9);
    const dark = [118, 108, 96], light = [232, 226, 214];
    for (let i = 0; i < 32; i++) { K.P(i, 31, dark); K.P(31, i, dark); K.P(i, 30, [160, 150, 138]); K.P(30, i, [160, 150, 138]); K.P(i, 0, light); K.P(0, i, light); }
    K.L(5, 6, 10, 10, [150, 140, 128]); K.L(10, 10, 9, 14, [150, 140, 128]); K.L(21, 19, 26, 23, [156, 146, 134]);
    for (const [x, y] of [[23, 7], [7, 23], [16, 26]]) { K.R(x, y, 2, 2, [168, 158, 146]); K.P(x, y, [226, 220, 206]); }
  }, 7), true));
}
function wallSideTex() {                    // 벽 옆면: 엇갈려 쌓은 벽돌
  const lt = tileTex('wall_side'); if (lt) return lt;
  return pxMemo('wside', () => pxTex(pxCanvas(32, 32, K => {
    K.R(0, 0, 32, 32, [78, 68, 58]);
    for (let r = 0; r < 4; r++) {
      const y0 = r * 8, off = r % 2 ? 8 : 0;
      for (let bx = -16; bx < 32; bx += 16) {
        const x0 = bx + off + 1;
        K.noise(x0, y0 + 1, 14, 6, [184, 170, 150], 10);
        K.R(x0, y0 + 1, 14, 1, [214, 202, 182]); K.R(x0, y0 + 6, 14, 1, [130, 118, 100]); K.R(x0, y0 + 1, 1, 6, [204, 192, 172]);
      }
    }
  }, 11), true));
}
function wallTopTex() {                     // 벽 윗면: 밝은 덮개돌
  const lt = tileTex('wall_top'); if (lt) return lt;
  return pxMemo('wtop', () => pxTex(pxCanvas(32, 32, K => {
    K.noise(0, 0, 32, 32, [226, 218, 204], 8);
    for (let i = 0; i < 32; i++) { K.P(i, 0, [250, 246, 236]); K.P(0, i, [250, 246, 236]); K.P(i, 31, [140, 130, 116]); K.P(31, i, [140, 130, 116]); }
    K.L(9, 11, 14, 15, [170, 160, 146]); K.L(20, 22, 24, 21, [170, 160, 146]);
  }, 13), true));
}
function rockPxTex() {
  return pxMemo('rock', () => pxTex(pxCanvas(32, 32, K => { K.noise(0, 0, 32, 32, [150, 136, 118], 26); for (let k = 0; k < 6; k++) { const x = Math.floor(K.rn() * 28), y = Math.floor(K.rn() * 28); K.L(x, y, x + 4, y + 3, [96, 86, 74]); } }, 17), true));
}
function cliffTex() {                      // 낭떠러지 벽: 바위 지층, 아래로 갈수록 어둠
  return pxMemo('cliff', () => { const t = pxTex(pxCanvas(32, 64, K => {
    for (let y = 0; y < 64; y++) for (let x = 0; x < 32; x++) {
      const k = Math.max(0, 1 - y / 44), n = (K.rn() - 0.5) * 26, band = (y % 9 === 0 || (y + (x >> 3)) % 13 === 0) ? -30 : 0;
      const v = Math.max(0, (118 + n + band) * k);
      K.P(x, y, [v, v * 0.9, v * 0.76]);
    }
    for (let i = 0; i < 32; i++) { K.P(i, 0, [176, 160, 136]); K.P(i, 1, [140, 126, 106]); }
  }, 47)); t.wrapS = THREE.RepeatWrapping; t.repeat.set(4, 1); return t; });
}
function pitTex() {                         // 구덩이: 무너진 돌 테두리와 끝없이 어두운 속
  return pxMemo('pit', () => pxTex(pxCanvas(32, 32, K => {
    K.noise(0, 0, 32, 32, [92, 82, 70], 10);
    K.E(16, 16, 14.5, 13.5, null, () => { const v = 118 + Math.round((K.rn() - 0.5) * 30); return [v, v - 10, v - 24]; });
    K.E(16, 16.5, 12, 11, [46, 34, 24]); K.E(16, 17, 9.5, 9, [24, 16, 10]); K.E(16, 17.5, 7, 6.5, [8, 5, 3]); K.E(16, 18, 4, 3.5, [0, 0, 0]);
    for (let k = 0; k < 9; k++) { const a = k / 9 * Math.PI * 2, x = Math.round(16 + Math.cos(a) * 13), y = Math.round(16 + Math.sin(a) * 12.5); K.R(x - 1, y - 1, 3, 2, [150, 138, 120]); K.P(x - 1, y - 1, [196, 184, 166]); }
  }, 19)));
}
function oreTex(n) {                        // 금맥: 바위 둔덕 위로 남은 양만큼 금 결정
  return pxMemo('ore' + n, () => pxTex(pxCanvas(32, 32, K => {
    K.E(16, 26, 13.5, 5.5, null, (x, y, dx, dy) => dy < -0.35 ? '#6a5642' : dy > 0.4 ? '#2e241c' : (K.rn() < 0.15 ? '#3c3026' : '#4a3c30'));
    const spots = [[16, 25, 15], [10, 26, 11], [22, 26, 11], [13, 28, 7], [20, 28, 8], [6, 28, 6], [26, 28, 6]];
    for (let k = 0; k < n; k++) {
      const [cx, by, hh] = spots[k], y0 = by - hh;
      K.R(cx - 1, y0 + 2, 4, hh - 2, '#ffc63a'); K.R(cx, y0, 2, 2, '#ffc63a');
      K.R(cx - 1, y0 + 2, 1, hh - 2, '#fff0a0'); K.P(cx, y0, '#fff6c8'); K.R(cx + 2, y0 + 2, 1, hh - 2, '#c08010'); K.P(cx + 1, y0 + 1, '#e0a020');
    }
    K.outline('#1a1008');
  }, 23)));
}
function campTex(team, dead, fr) {          // 야영지: 팀 색 천막 · 깃발 · 울타리 · 모닥불 · 금 더미
  return pxMemo('camp' + team + dead + fr, () => pxTex(pxCanvas(48, 48, K => {
    const T = teamHex(team, 'c'), Td = teamHex(team, 'd'), Tl = teamHex(team, 'l');
    K.E(24, 40, 22, 7, null, (x, y, dx, dy) => dy < -0.45 ? '#8a765c' : dy > 0.5 ? '#4a3c2c' : (K.rn() < 0.12 ? '#5a4a38' : '#6b5a44'));
    for (let i = 0; i < 9; i++) { const x = 4 + i * 5; K.R(x, 29, 2, 8, '#6a4522'); K.P(x, 28, '#8a6038'); K.P(x + 1, 29, '#4a2e14'); }
    K.R(4, 31, 42, 1, '#4a2e14');
    if (!dead) {
      for (let y = 8; y <= 40; y++) { const half = (y - 8) * 0.56, x0 = Math.round(24 - half), x1 = Math.round(24 + half); for (let x = x0; x <= x1; x++) K.P(x, y, x < 24 ? T : Td); }
      K.L(24, 8, 15, 40, Tl); K.L(24, 8, 33, 40, shade(Td, -0.2));
      for (let y = 25; y <= 40; y++) { const half = (y - 25) * 0.42; K.R(Math.round(24 - half), y, Math.round(half * 2) + 1, 1, '#1a0f08'); }
      K.R(23, 1, 2, 8, '#6a4522');
      for (let x = 25; x <= 34; x++) { const y0 = 2 + Math.round(Math.sin((x - 25) * 0.7 + fr * 1.7) * 1.2); K.R(x, y0, 1, 5, x === 34 ? Td : Tl); K.P(x, y0, '#ffffff'); }
      K.R(35, 41, 9, 2, '#5a3414'); K.L(35, 43, 43, 40, '#7a4c26', 2);
      if (fr) { K.E(39.5, 35, 3, 5, '#ff6a14'); K.E(39.5, 37, 1.8, 3, '#ffe08a'); K.P(41, 28, '#ffb040'); }
      else { K.E(39.5, 35.5, 3.3, 4.5, '#ff7a1a'); K.E(40, 37, 2, 2.6, '#ffe08a'); K.P(38, 29, '#ffb040'); }
      K.E(9, 41, 5, 2.5, '#c08a10'); K.E(9, 40, 4, 2, '#ffc63a'); K.P(8, 39, '#fff0a0'); K.P(11, 40, '#fff0a0'); K.E(9, 38.5, 2, 1, '#ffd24a');
    } else {
      for (let y = 28; y <= 40; y++) { const half = Math.min(16, (y - 28) * 1.4), x0 = Math.round(24 - half); for (let x = x0; x <= x0 + half * 2; x++) if (K.rn() > 0.12) K.P(x, y, (x + y) % 5 ? shade(Td, -0.35) : shade(T, -0.3)); }
      K.L(18, 40, 30, 24, '#4a2e14', 2); K.E(39, 40, 4, 1.5, '#3a3430'); K.P(38, 39, '#5a5048');
    }
    K.outline('#140c06');
  }, 29 + team)));
}
function clockTex(step, n) {               // 금맥이 다시 자라는 시계: 금빛 막대가 차오른다
  return pxMemo('clk' + step + ':' + n, () => pxTex(pxCanvas(36, 7, K => {
    K.R(0, 0, 36, 7, '#140c06'); K.R(1, 1, 34, 5, '#3a2e22');
    const w = Math.round(34 * step / n);
    if (w) { K.R(1, 1, w, 5, '#ffc63a'); K.R(1, 1, w, 1, '#fff0a0'); K.R(1, 5, w, 1, '#c08010'); }
    for (let i = 1; i < 4; i++) K.R(1 + Math.round(34 * i / 4), 1, 1, 5, '#140c06');
  })));
}
function lootTex(big) {                     // 떨어진 금: 자루 (작은 양) · 보물 상자 (큰 양)
  return pxMemo('loot' + big, () => pxTex(big ? pxCanvas(28, 24, K => {
    K.R(3, 11, 22, 11, '#6a4020'); for (const y of [14, 18]) K.R(3, y, 22, 1, '#4a2a12');
    K.R(3, 7, 22, 4, '#7a4c26'); K.R(3, 7, 22, 1, '#9a6438');
    K.E(14, 7, 8, 3, '#ffc63a', (x, y, dx, dy) => dy < -0.3 ? '#fff0a0' : (K.rn() < 0.2 ? '#c08a10' : '#ffc63a'));
    K.R(6, 7, 2, 15, '#3a3a3e'); K.R(20, 7, 2, 15, '#3a3a3e'); K.R(13, 12, 3, 3, '#ffc63a'); K.P(14, 13, '#2a1600');
    K.outline('#140c06');
  }, 31) : pxCanvas(20, 20, K => {
    K.E(10, 13.5, 7, 5.5, null, (x, y, dx, dy) => dx < -0.35 && dy < 0 ? '#a87040' : dx > 0.4 || dy > 0.5 ? '#6a4020' : '#8a5a2a');
    K.R(8, 5, 4, 4, '#8a5a2a'); K.R(7, 4, 6, 1, '#6a4020'); K.R(8, 8, 4, 1, '#ffc63a');
    K.R(15, 17, 3, 2, '#ffc63a'); K.P(16, 17, '#fff0a0'); K.R(2, 17, 3, 1, '#ffc63a');
    K.outline('#140c06');
  }, 37)));
}
function garrowTex() {                      // 바닥에 비스듬히 꽂힌 화살
  return pxMemo('garrow', () => pxTex(pxCanvas(16, 20, K => {
    K.L(5, 17, 11, 5, '#d8c08a'); K.L(6, 17, 12, 5, '#a8884a');
    K.L(10, 2, 11, 6, '#f4f0e0'); K.L(12, 1, 13, 5, '#f4f0e0'); K.P(11, 1, '#e04030'); K.P(13, 4, '#e04030');
    K.R(3, 18, 5, 1, '#3a2a1a');
    K.outline('#140c06');
  }, 41)));
}
function brazierTex(fr) {                   // 모서리 화로 기둥
  return pxMemo('braz' + fr, () => pxTex(pxCanvas(16, 40, K => {
    K.R(3, 36, 10, 4, '#5a4632'); K.R(3, 36, 10, 1, '#7a6448');
    K.R(5, 14, 6, 22, '#7d6648'); K.R(5, 14, 1, 22, '#a08868'); K.R(10, 14, 1, 22, '#5a4632');
    for (let y = 18; y < 36; y += 6) K.R(5, y, 6, 1, '#5a4632');
    K.R(2, 11, 12, 3, '#8a6a3a'); K.R(2, 11, 12, 1, '#c09858'); K.R(3, 14, 10, 1, '#6a4a2a');
    if (fr) { K.E(8, 6, 3.5, 5.5, '#ff6a14'); K.E(8, 8, 2, 3, '#ffe08a'); K.P(10, 0, '#ffb040'); }
    else { K.E(8, 6.5, 4, 5, '#ff7a1a'); K.E(7.5, 8, 2.3, 2.8, '#ffe08a'); K.P(5, 1, '#ffb040'); }
    K.outline('#140c06');
  }, 43)));
}

function glowTex(kind, team, fr) {          // 마우스를 올렸을 때: 도트 테두리를 팀 색으로 (한 칸 더 두껍게)
  return pxMemo('glow' + kind + team + ':' + fr, () => {
    const src = bodyCanvas(kind, team, fr), w = src.width, h = src.height;
    const sd = src.getContext('2d').getImageData(0, 0, w, h).data;
    const A = (x, y) => x >= 0 && y >= 0 && x < w && y < h ? sd[(y * w + x) * 4 + 3] : 0;
    const dark = (x, y) => { const i = (y * w + x) * 4; return sd[i + 3] && sd[i] < 40 && sd[i + 1] < 30 && sd[i + 2] < 24; };
    const col = rgbOf(team >= 0 ? '#' + TC[team].l.toString(16).padStart(6, '0') : '#c8ff70'), hot = shade(col, 0.5);
    return pxTex(pxCanvas(w, h, K => {
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        if (dark(x, y)) K.P(x, y, hot);
        else if (!A(x, y)) { let n = 0; for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) if (A(x + dx, y + dy)) n++; if (n) K.P(x, y, col); }
      }
    }));
  });
}
function hpTex(k10, team) {                  // 머리 위 체력바: 둥근 끝, 검은 테, 팀 색 (낮으면 주황)
  return pxMemo('hp' + k10 + ':' + team, () => pxTex(pxCanvas(40, 7, K => {
    K.R(1, 0, 38, 7, '#0b0705'); K.R(0, 1, 40, 5, '#0b0705');
    K.R(2, 1, 36, 5, '#2c2620'); K.R(1, 2, 38, 3, '#2c2620');
    const c = k10 <= 3 ? '#ff7a3d' : team >= 0 ? TC[team].css : '#9adf3a', w = Math.round(38 * k10 / 10);
    if (w) { K.R(1, 2, w, 3, c); K.R(Math.min(2, w), 1, Math.max(0, Math.min(w, 37) - 1), 5, c); K.R(2, 1, Math.max(0, Math.min(w, 37) - 1), 1, shade(c, 0.45)); K.R(2, 5, Math.max(0, Math.min(w, 37) - 1), 1, shade(c, -0.3)); }
  })));
}
let hoverC = null;
// ---------------- LPC 캐릭터 시트 (있으면 도트 그림 대신 쓴다) ----------------
const SP = window.SPRITES || null, SHEETS = {};
if (SP) await Promise.all(Object.entries(SP.img).map(([name, url]) => new Promise(res => {
  const img = new Image();
  img.onload = () => {
    const m = SP.meta.sheets[name], t = new THREE.Texture(img);
    t.colorSpace = THREE.SRGBColorSpace; t.magFilter = t.minFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true;
    // 마우스를 올렸을 때 쓸 테두리 시트: 그림 바깥 한 칸을 팀 색으로
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const sd = g.getImageData(0, 0, c.width, c.height), a = sd.data, W2 = c.width, H2 = c.height;
    const od = g.createImageData(W2, H2), o = od.data;
    const tc = name.endsWith('_0') ? TC[0].l : name.endsWith('_1') ? TC[1].l : 0xc8ff70, cr = tc >> 16 & 255, cg = tc >> 8 & 255, cb = tc & 255;
    for (let y = 0; y < H2; y++) for (let x = 0; x < W2; x++) {
      const i = (y * W2 + x) * 4;
      if (a[i + 3]) continue;
      let n = 0;
      for (let dy = -1; dy <= 1 && !n; dy++) for (let dx = -1; dx <= 1; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < W2 && yy < H2 && a[(yy * W2 + xx) * 4 + 3]) { n = 1; break; } }
      if (n) { o[i] = cr; o[i + 1] = cg; o[i + 2] = cb; o[i + 3] = 255; }
    }
    g.putImageData(od, 0, 0);
    const gt = new THREE.CanvasTexture(c); gt.colorSpace = THREE.SRGBColorSpace; gt.magFilter = gt.minFilter = THREE.NearestFilter; gt.generateMipmaps = false;
    SHEETS[name] = {img, m, tex: t, glow: gt};
    res();
  };
  img.onerror = () => res();
  img.src = url;
})));
const shadowMat = new THREE.MeshBasicMaterial({map: softTex(), color: 0x000000, transparent: true, opacity: 0.55, depthWrite: false});
const shadowG = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
function makeShadow(w, d) {                       // 발밑의 부드러운 그림자 (Cambridge 처럼)
  const m = new THREE.Mesh(shadowG, shadowMat); m.scale.set(w, 1, d); m.position.y = 0.006; m.renderOrder = 3; return m;
}
function decoTex(v) {                            // 바닥 장식: 작은 돌 · 이끼 · 뼈 조각 (아주 옅게)
  return pxMemo('deco' + v, () => pxTex(pxCanvas(32, 32, K => {
    if (v === 0) { for (const [x, y, r] of [[9, 20, 2.2], [14, 23, 1.5], [22, 12, 1.8]]) { K.E(x, y, r + 0.6, r, '#5e5a54'); K.P(x - 1, y - 1, '#8c887e'); K.P(x, y + Math.ceil(r), '#2e2c28'); } }
    else if (v === 1) { for (let k = 0; k < 26; k++) { const x = 6 + Math.floor(K.rn() * 20), y = 8 + Math.floor(K.rn() * 16); K.P(x, y, K.rn() < 0.5 ? '#3a5a2a' : '#4e7036'); if (K.rn() < 0.4) K.P(x + 1, y, '#2c4420'); } }
    else { K.L(11, 18, 19, 15, '#8a8270', 1); K.E(10, 18, 1.2, 1.2, '#9a927e'); K.E(20, 15, 1.2, 1.2, '#9a927e'); }
  }, 61 + v), true));
}
function rimTex(mask, v) {                       // 벽 윗면 한 칸: 바위 질감 + 열린 가장자리의 들쭉날쭉한 테두리 (위 · 왼쪽 밝게, 아래 · 오른쪽 어둡게)
  return pxMemo('rim' + mask + ':' + v, () => {
    const c = document.createElement('canvas'); c.width = c.height = 32;
    const g = c.getContext('2d'); g.drawImage(SHEETS.wall_top.img, 0, 0, 32, 32);
    const d = g.getImageData(0, 0, 32, 32), a = d.data, rn = rnd(131 + mask * 17 + v * 5);
    const open = [!(mask & 1), !(mask & 2), !(mask & 4), !(mask & 8)];     // 북 · 동 · 남 · 서 가장자리가 바닥과 닿는가
    const jag = [0, 1, 2, 3].map(() => Array.from({length: 32}, () => 1 + Math.floor(rn() * 2.6)));
    for (let y = 0; y < 32; y++) for (let x = 0; x < 32; x++) {
      const i = (y * 32 + x) * 4, dist = [y, 31 - x, 31 - y, x], along = [x, y, x, y];
      let best = null;
      for (let k = 0; k < 4; k++) if (open[k] && dist[k] <= jag[k][along[k]] + 1) { if (!best || dist[k] < best[1]) best = [k, dist[k], jag[k][along[k]]]; }
      // 두 열린 가장자리가 만나는 모서리는 둥글게 깎는다
      const cn = (open[0] && open[3] && x + y < 4) || (open[0] && open[1] && (31 - x) + y < 4) || (open[2] && open[1] && (31 - x) + (31 - y) < 4) || (open[2] && open[3] && x + (31 - y) < 4);
      if (cn || (best && best[1] === 0)) { a[i] = 26; a[i + 1] = 22; a[i + 2] = 18; continue; }   // 바깥 테두리 (어두운 선)
      if (!best) continue;
      const [k, dd, dep] = best, lit = k === 0 || k === 3;
      const f = dd <= dep ? (lit ? 1.45 : 0.62) : (lit ? 1.18 : 0.8);
      a[i] = Math.min(255, a[i] * f); a[i + 1] = Math.min(255, a[i + 1] * f); a[i + 2] = Math.min(255, a[i + 2] * f);
    }
    g.putImageData(d, 0, 0);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.magFilter = THREE.NearestFilter; t.minFilter = THREE.LinearMipmapLinearFilter;
    return t;
  });
}
function perceptStrip(keys) {                    // 지각 아이콘 여러 개를 한 줄 띠로
  return pxMemo('ps_' + keys.join(','), () => {
    const c = document.createElement('canvas'); c.width = 15 * keys.length + 1; c.height = 15;
    const g = c.getContext('2d'); g.imageSmoothingEnabled = false;
    keys.forEach((k, i) => g.drawImage(perceptTex(k).image, 1 + i * 15, 0));
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.magFilter = t.minFilter = THREE.NearestFilter; t.generateMipmaps = false;
    return t;
  });
}
function outlined(c) {                           // 그림 둘레에 어두운 테 1픽셀 (배경 원 없이도 어디서나 읽히게)
  const g = c.getContext('2d'), w = c.width, h = c.height, im = g.getImageData(0, 0, w, h), D = im.data, S = D.slice();
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    if (S[i + 3]) continue;
    let near = false;
    for (let dy = -1; dy <= 1 && !near; dy++) for (let dx = -1; dx <= 1; dx++) {
      const X = x + dx, Y = y + dy;
      if (X >= 0 && Y >= 0 && X < w && Y < h && S[(Y * w + X) * 4 + 3]) { near = true; break; }
    }
    if (near) { D[i] = 14; D[i + 1] = 9; D[i + 2] = 6; D[i + 3] = 235; }
  }
  g.putImageData(im, 0, 0);
  return c;
}
function perceptDot() {                          // '선택만' 표시에서 나머지 모험가 머리 위에 찍는 작은 점 (느끼는 것이 있다는 뜻)
  return pxMemo('pc_dot', () => pxTex(outlined(pxCanvas(5, 5, K => { K.R(1, 1, 3, 3, '#ffe9b0'); }))));
}
function perceptTex(k) {                       // 지각 도트 아이콘 (머리 위. 발소리만 발밑 칸에 그린다)
  return pxMemo('pc_' + k, () => pxTex(outlined(pxCanvas(14, 14, K => {
    if (k === 'breeze') { K.L(3, 5, 10, 5, '#bfe9ff'); K.L(4, 8, 11, 8, '#8fd0ff'); K.L(3, 11, 8, 11, '#bfe9ff'); K.P(10, 4, '#bfe9ff'); K.P(11, 7, '#8fd0ff'); }
    else if (k === 'stench') { for (const x of [4, 7, 10]) { K.L(x, 11, x + 1, 8, '#9adf3a'); K.L(x + 1, 8, x, 4, '#c8ff6a'); } }
    else if (k === 'glitter') { K.L(7, 2, 7, 12, '#ffe070'); K.L(2, 7, 12, 7, '#ffe070'); K.R(6, 6, 3, 3, '#fff8d0'); K.P(4, 4, '#ffc63a'); K.P(10, 10, '#ffc63a'); K.P(10, 4, '#ffc63a'); K.P(4, 10, '#ffc63a'); }
    else if (k === 'bump') { K.R(6, 2, 2, 7, '#ff9a40'); K.R(6, 10, 2, 2, '#ff9a40'); }
    else if (k === 'steps') { K.E(5, 5, 1.6, 2.2, '#e8dcc4'); K.E(9, 9, 1.6, 2.2, '#e8dcc4'); K.P(5, 8, '#e8dcc4'); K.P(9, 12, '#e8dcc4'); }
    else if (k === 'hurt') { K.E(5, 6, 2.2, 2.2, '#ff4a3a'); K.E(9, 6, 2.2, 2.2, '#ff4a3a'); K.L(3, 7, 7, 11, '#ff4a3a', 2); K.L(11, 7, 7, 11, '#ff4a3a', 2); }
  }))));
}
let _ring = null;
function footRingTex() {                         // 발밑 팀 표시: 그 칸이 팀 색으로 옅게 빛난다 (가장자리는 조금 더 밝게, 모서리는 둥글게)
  if (_ring) return _ring;
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), d = g.createImageData(64, 64);
  for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) {
    const e = Math.min(x, y, 63 - x, 63 - y), i = (y * 64 + x) * 4;           // 칸 가장자리까지 거리
    const cx = Math.max(0, 5 - Math.min(x, 63 - x)), cy = Math.max(0, 5 - Math.min(y, 63 - y)), corner = Math.hypot(cx, cy) > 5;
    const al = corner ? 0 : e < 2 ? 0.5 + e * 0.2 : 0.42 + 0.48 * Math.exp(-(e - 2) / 5);
    d.data[i] = d.data[i + 1] = d.data[i + 2] = 255; d.data[i + 3] = Math.round(255 * al);
  }
  g.putImageData(d, 0, 0);
  _ring = new THREE.CanvasTexture(c); _ring.colorSpace = THREE.SRGBColorSpace;
  return _ring;
}
const _gold = new Map();
function goldTex(n, full) {                      // 든 금: 금화 한 닢 위에 숫자 (가득 차면 밝은 테)
  const key = n + (full ? 'f' : '');
  if (_gold.has(key)) return _gold.get(key);
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d');
  const disc = (r, f, dx = 0, dy = 0) => { g.beginPath(); g.arc(32 + dx, 32 + dy, r, 0, 7); g.fillStyle = f; g.fill(); };
  disc(31, '#0b0705');                           // 검은 테: 어떤 바탕 위에서도 또렷하게
  disc(27, full ? '#fff3b0' : '#8a5a10');
  disc(24, '#e8a820');
  disc(21, '#ffcf45', -1, -1.5);
  g.fillStyle = 'rgba(255,255,255,0.55)'; g.beginPath(); g.ellipse(24, 20, 9, 4, -0.6, 0, 7); g.fill();
  g.font = '900 36px "Arial Black", Arial, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.lineWidth = 5; g.strokeStyle = '#fff6cf'; g.lineJoin = 'round'; g.strokeText(String(n), 32, 34.5);
  g.fillStyle = '#2a1400'; g.fillText(String(n), 32, 34.5);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  _gold.set(key, t);
  return t;
}
function coinTex() {                              // 도트 금화
  return pxMemo('coin', () => pxTex(pxCanvas(10, 10, K => {
    K.E(5, 5, 4.2, 4.2, '#e8a820'); K.E(4.6, 4.6, 3, 3, '#ffd24a'); K.P(3, 3, '#fff6c0'); K.P(4, 3, '#fff6c0'); K.R(5, 4, 1, 3, '#b07810');
    K.outline('#3a2000');
  })));
}
function beamTex() {                              // 도트 빛기둥 (위로 갈수록 성기게 사라짐)
  return pxMemo('beam', () => pxTex(pxCanvas(12, 48, K => {
    for (let y = 0; y < 48; y++) for (let x = 0; x < 12; x++) {
      const c = Math.abs(x - 5.5) / 6, f = y / 48;
      if (c > 0.85) continue;
      if ((x + y) % 2 && f < 0.35) continue;      // 위쪽은 체크무늬로 성기게
      const v = c < 0.3 ? 255 : c < 0.6 ? 200 : 150;
      K.P(x, y, [v, v, v]);
    }
  })));
}
function slashTex() {                             // 근접 공격의 도트 베기 호
  return pxMemo('slash', () => pxTex(pxCanvas(32, 32, K => {
    for (let a = -1.25; a <= 1.25; a += 0.02) {
      const w = 3 * Math.cos(a * 1.2);
      for (let r = 11; r < 11 + w; r += 0.5) K.P(16 + Math.cos(a) * r, 16 + Math.sin(a) * r, r > 10 + w ? [255, 230, 160] : [255, 255, 255]);
    }
  })));
}
function frameSprite(name, col, w, h, cy) {     // 한 줄짜리 LPC 시트의 한 칸 (떨어진 금 · 횃불 기둥 등)
  const S = SHEETS[name]; if (!S) return null;
  const t = S.tex.clone(); t.repeat.set(1 / S.m.cols, 1); t.offset.set(col / S.m.cols, 0); t.needsUpdate = true;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: t, transparent: true, alphaTest: 0.5}));
  sp.center.set(0.5, cy); sp.scale.set(w, h, 1); sp.renderOrder = 5; sp.userData.cols = S.m.cols;
  return sp;
}
const AGENT = () => typeof R !== 'undefined' && R && R.const && R.const.rules && R.const.rules.agent;   // 시안 3 (모험가) 리플레이인가
function sheetName(kind, team) { return kind === 'E' ? (AGENT() && SHEETS['adventurer_' + team] ? 'adventurer_' : 'explorer_') + team : kind === 'G' ? 'archer_' + team : kind === 'W' ? 'wumpus' : null; }
function lpcFrame(sp, anim, dir, col) {        // 시트의 한 칸 (동작 · 방향 · 칸 번호) 을 보이게
  const L = sp.userData.lpc; if (!L) return;
  const A = L.m[anim], row = A.row + (A.dirs > 1 ? dir : 0), c = Math.max(0, Math.min(A.n - 1, col));
  sp.material.map.offset.set(c / L.m.cols, 1 - (row + 1) / L.m.rows);
}
function lpcDir(th) { const k = ((Math.round(th / (Math.PI / 2)) % 4) + 4) % 4; return [2, 3, 0, 1][k]; }   // 남 · 동 · 북 · 서 → 시트 줄 (위 0, 왼 1, 아래 2, 오른 3)
function lpcSprite(name, h, glow) {
  const S = SHEETS[name], t = (glow ? S.glow : S.tex).clone();
  t.repeat.set(1 / S.m.cols, 1 / S.m.rows); t.needsUpdate = true;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial(glow ? {map: t, transparent: true, depthTest: false, blending: THREE.AdditiveBlending} : {map: t, transparent: true, alphaTest: 0.5}));
  { const cl = S.m.cell || SP.meta.cell, ft = S.m.foot || SP.meta.foot; sp.center.set(0.5, (cl - ft) / cl); }
  sp.scale.set(h, h, 1);
  sp.userData.w = h; sp.userData.lpc = {m: S.m};
  sp.renderOrder = glow ? 12 : 6;
  lpcFrame(sp, 'idle', 2, 0);
  return sp;
}
function makeBody(kind, team, h) {
  const nm = sheetName(kind, team);
  if (nm && SHEETS[nm]) return lpcSprite(nm, h * (SHEETS[nm].m.scale || (kind === 'W' ? 2.1 : 2.6)));
  const w = kind === 'W' ? h : h * 16 / 24;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: bodyTex(kind, team, 0), transparent: true, alphaTest: 0.5}));
  sp.center.set(0.5, 0.02);
  sp.scale.set(w, h, 1);
  sp.userData.w = w;
  sp.renderOrder = 6;
  return sp;
}

// ---------------- 동굴 지형: 이어진 바닥 · 솟은 바위 · 구덩이 ----------------
function vnoise(seed, P) {                       // 주기 P 인 부드러운 값 잡음 (이어 붙여도 끊기지 않는다)
  const rn = rnd(seed), a = new Float32Array(P * P); for (let i = 0; i < P * P; i++) a[i] = rn();
  return (x, y) => {
    x = ((x % P) + P) % P; y = ((y % P) + P) % P;
    const x0 = Math.floor(x) % P, y0 = Math.floor(y) % P, fx = x - Math.floor(x), fy = y - Math.floor(y), x1 = (x0 + 1) % P, y1 = (y0 + 1) % P, sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    return (a[y0 * P + x0] * (1 - sx) + a[y0 * P + x1] * sx) * (1 - sy) + (a[y1 * P + x0] * (1 - sx) + a[y1 * P + x1] * sx) * sy;
  };
}
function caveFloorTex() {                        // 동굴 바닥: 여덟 칸 (256px) 마다 되풀이. 칸 테두리 줄 없이 얼룩 · 금 · 자갈, 칸 모서리에 옅은 자국 (칸 줄은 build 의 격자가 긋는다)
  return pxMemo('cavefloor', () => {
    const N = 256, n1 = vnoise(11, 4), n2 = vnoise(12, 8), n3 = vnoise(13, 16), n4 = vnoise(14, 64);
    const pal = ['#39414a', '#4b545d', '#5e6871', '#727c85', '#87919a', '#9da6ae'];
    const c = pxCanvas(N, N, K => {
      const Wp = v => ((Math.round(v) % N) + N) % N;
      for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
        const u = x / N, v = y / N;
        let t = 0.3 * n1(u * 4, v * 4) + 0.3 * n2(u * 8, v * 8) + 0.4 * n3(u * 16, v * 16);
        t += (n4(u * 64, v * 64) - 0.5) * 0.34 + (K.rn() - 0.5) * 0.16;      // 알갱이: 매끈한 얼룩이 아니라 거친 돌바닥
        K.P(x, y, pal[Math.max(0, Math.min(5, Math.floor((t - 0.24) / 0.52 * 6)))]);
      }
      for (let k = 0; k < 16; k++) {                 // 갈라진 금
        let x = K.rn() * N, y = K.rn() * N, a = K.rn() * 6.28; const len = 16 + K.rn() * 46;
        for (let i = 0; i < len; i++) { K.P(Wp(x), Wp(y), '#262b30'); if (K.rn() < 0.3) K.P(Wp(x + 1), Wp(y + 1), '#a3aab0'); a += (K.rn() - 0.5) * 0.9; x += Math.cos(a); y += Math.sin(a); }
      }
      for (let k = 0; k < 80; k++) {                 // 박힌 자갈: 왼쪽 위는 밝게, 오른쪽 아래는 그늘
        const x = Math.floor(K.rn() * N), y = Math.floor(K.rn() * N), r = 1 + Math.floor(K.rn() * 2.5);
        for (let j = -r; j <= r; j++) for (let i = -r; i <= r; i++) if (i * i + j * j <= r * r + 0.5) K.P(Wp(x + i), Wp(y + j), i + j < -r * 0.6 ? '#b8bec3' : i + j > r * 0.8 ? '#353b40' : '#8a9198');
        for (let i = -r + 1; i <= r + 1; i++) K.P(Wp(x + i), Wp(y + r + 1), '#2b3035');
      }
      for (let j = 0; j < 8; j++) for (let i = 0; i < 8; i++) {   // 칸 모서리: 작은 홈 (줄은 긋지 않는다)
        if (K.rn() < 0.12) continue;
        const x = i * 32, y = j * 32, col = '#2b3035';
        K.P(Wp(x), Wp(y), col); K.P(Wp(x - 1), Wp(y), col); K.P(Wp(x), Wp(y - 1), col);
        if (K.rn() < 0.6) K.P(Wp(x + 1), Wp(y), col); if (K.rn() < 0.6) K.P(Wp(x), Wp(y + 1), col); if (K.rn() < 0.4) K.P(Wp(x - 1), Wp(y - 1), '#a3aab0');
      }
    }, 91);
    const t = pxTex(c, true); t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
  });
}
function caveRockTex() {                         // 바위 겉: 회갈색 얼룩과 가는 금
  return pxMemo('caverock', () => {
    const N = 64, n1 = vnoise(21, 4), n2 = vnoise(22, 16);
    const pal = ['#9aa1a8', '#adb3b9', '#bec4c9', '#cfd3d7', '#dfe2e5'];
    const c = pxCanvas(N, N, K => {
      const Wp = v => ((Math.round(v) % N) + N) % N;
      for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
        const t = 0.25 * n1(x / N * 4, y / N * 4) + 0.5 * n2(x / N * 16, y / N * 16) + 0.25 * K.rn();
        K.P(x, y, pal[Math.max(0, Math.min(4, Math.floor((t - 0.22) / 0.56 * 5)))]);
      }
      for (let k = 0; k < 7; k++) { let x = K.rn() * N, y = K.rn() * N, a = K.rn() * 6.28; const len = 6 + K.rn() * 14;
        for (let i = 0; i < len; i++) { K.P(Wp(x), Wp(y), '#6c737a'); a += (K.rn() - 0.5) * 0.8; x += Math.cos(a); y += Math.sin(a); } }
    }, 93);
    const t = pxTex(c, true); t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
  });
}
function worldUv(mat) {                          // 칸마다 같은 그림을 찍지 않고, 바닥 전체에 한 장을 이어 깐다 (8칸마다 되풀이)
  mat.onBeforeCompile = sh => {
    sh.uniforms.uOff = {value: new THREE.Vector2(W / 2, H / 2)};
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform vec2 uOff;')
      .replace('#include <uv_vertex>', `#include <uv_vertex>
#ifdef USE_MAP
  #ifdef USE_INSTANCING
    vec4 wp_ = modelMatrix * instanceMatrix * vec4(position, 1.0);
  #else
    vec4 wp_ = modelMatrix * vec4(position, 1.0);
  #endif
  vMapUv = (wp_.xz + uOff) / 8.0;
#endif`);
  };
  mat.customProgramCacheKey = () => 'worlduv' + W + 'x' + H;
  return mat;
}
function pitHoleTex(v) {                         // 구덩이: 바닥이 무너져 뚫린 구멍. 들쭉날쭉한 가장자리, 건너편 안벽의 지층, 그 아래는 어둠
  return pxMemo('pithole' + v, () => pxTex(pxCanvas(48, 48, K => {
    const an = vnoise(40 + v, 12);
    for (let y = 0; y < 48; y++) for (let x = 0; x < 48; x++) {
      const dx = (x + 0.5 - 24) / 24, dy = (y + 0.5 - 24) / 24, r = Math.hypot(dx, dy), th = Math.atan2(dy, dx);
      const R0 = 0.72 + 0.16 * an((th / 6.2832 + 0.5) * 12, 0.5);
      if (r > R0 + 0.12) continue;
      if (r > R0) { K.P(x, y, dy < -0.15 ? (K.rn() < 0.6 ? '#8f8776' : '#6a6357') : (K.rn() < 0.5 ? '#2a2623' : '#48423b')); continue; }   // 부서진 테두리 (먼 쪽은 밝게)
      const dep = dy + Math.sqrt(Math.max(0, R0 * R0 - dx * dx));     // 건너편 (북쪽) 가장자리에서 아래로 내려온 거리
      if (dep < 0.62) { const q = dep / 0.62 + (K.rn() - 0.5) * 0.12; K.P(x, y, q < 0.2 ? '#5a5046' : q < 0.45 ? '#40382f' : q < 0.72 ? '#28221c' : '#14110e'); }
      else K.P(x, y, '#000000');
    }
  }, 57 + v)));
}
function buildRock(rows) {                        // 벽 = 바닥에서 솟은 바위. 벽 칸 안쪽으로 갈수록 높아지는 높이 지형을 삼각형으로 짠다 (지도 둘레는 동굴 벽)
  const k = 4, B = 3, GW = (W + 2 * B) * k, GH = (H + 2 * B) * k, NV = (GW + 1) * (GH + 1);
  const isFloor = (cx, cy) => (cx >= 0 && cy >= 0 && cx < W && cy < H) ? rows[cy][cx] !== '#' : false;
  const hn = vnoise(31, 64), X = new Float32Array(NV), Y = new Float32Array(NV), Z = new Float32Array(NV);
  for (let j = 0; j <= GH; j++) for (let i = 0; i <= GW; i++) {
    const x = i / k - B, y = j / k - B, cx0 = Math.floor(x), cy0 = Math.floor(y), id = j * (GW + 1) + i;
    let d = 2;                                    // 가장 가까운 바닥 칸까지 거리
    for (let cy = cy0 - 2; cy <= cy0 + 2; cy++) for (let cx = cx0 - 2; cx <= cx0 + 2; cx++) if (isFloor(cx, cy)) {
      const ddx = Math.max(cx - x, 0, x - cx - 1), ddy = Math.max(cy - y, 0, y - cy - 1); d = Math.min(d, Math.hypot(ddx, ddy)); }
    const out = Math.hypot(Math.max(-x, 0, x - W), Math.max(-y, 0, y - H));
    let top;
    if (out <= 0) top = 0.6 + 0.42 * hn(x * 0.9 + 7, y * 0.9 + 3) + 0.2 * Math.min(1, Math.max(0, d - 0.5));
    else if (y > H) top = Math.max(0, 0.36 * (1 - (y - H) / 2.4)) * (0.6 + 0.8 * hn(x * 1.3 + 50, y * 1.3 + 20));   // 남쪽 (카메라 쪽) 은 낮은 돌무더기
    else {
      const side = y < 0 ? 0.9 + out * 0.9 : (0.8 + out * 0.5) * Math.min(1, Math.max(0.3, (H + 0.5 - y) / 3));     // 북쪽은 높은 절벽, 옆은 중간
      top = side * (0.8 + 0.4 * hn(x * 1.3 + 50, y * 1.3 + 20));
    }
    const f = d <= 0 ? 0 : d >= 0.5 ? 0.78 + 0.44 * hash(i * 3 + 1, j * 7 + 2) : d <= 0.25 ? (0.7 + 0.3 * hash(i * 3 + 1, j * 7 + 2)) * (d / 0.25) : 0.8 + 0.3 * hash(i * 3 + 1, j * 7 + 2);
    const jit = d > 0 ? 0.11 : 0;
    X[id] = x - W / 2 + (hash(i, j * 3 + 11) - 0.5) * 2 * jit;
    Z[id] = y - H / 2 + (hash(i * 5 + 3, j) - 0.5) * 2 * jit;
    Y[id] = d <= 0 ? -0.03 : Math.max(0.02, f * top + (hash(i + 17, j + 29) - 0.5) * 0.12);
    if (d > 0 && top <= 0.001) Y[id] = -0.03;
  }
  const pos = [], col = [], uv = [], cells = [];
  const tri = (a, b, c, fi) => {
    const ya = (Y[a] + Y[b] + Y[c]) / 3;
    const e1x = X[b] - X[a], e1y = Y[b] - Y[a], e1z = Z[b] - Z[a], e2x = X[c] - X[a], e2y = Y[c] - Y[a], e2z = Z[c] - Z[a];
    const nx = e1y * e2z - e1z * e2y, ny = e1z * e2x - e1x * e2z, nz = e1x * e2y - e1y * e2x, nl = Math.hypot(nx, ny, nz) || 1;
    const up = Math.abs(ny) / nl, south = nz / nl * Math.sign(ny || 1);          // 윗면인가, 카메라 (남쪽) 를 보는 면인가
    let sh = 1.6 * (0.5 + 0.62 * up + 0.22 * Math.max(0, south)) * (0.72 + 0.3 * Math.min(1, Math.max(0, ya) / 0.8)) * (0.8 + 0.4 * hash(fi, 71));
    if (ya > 1.2) sh *= Math.max(0.12, 1 - (ya - 1.2) * 0.42);                  // 높은 절벽은 위로 갈수록 어둠 속으로
    const cx = Math.min(W - 1, Math.max(0, Math.floor((X[a] + X[b] + X[c]) / 3 + W / 2))), cy = Math.min(H - 1, Math.max(0, Math.floor((Z[a] + Z[b] + Z[c]) / 3 + H / 2)));
    for (const v of [a, b, c]) { pos.push(X[v], Y[v], Z[v]); col.push(sh, sh * 0.98, sh * 0.96); if (up > 0.6) uv.push(X[v] / 2, Z[v] / 2); else if (Math.abs(nx) > Math.abs(nz)) uv.push(Z[v] / 2, Y[v] / 2); else uv.push(X[v] / 2, Y[v] / 2); }   // 면이 향한 쪽으로 무늬를 편다 (늘어진 줄무늬 방지)
    cells.push(cy * W + cx);
  };
  for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) {
    const a = j * (GW + 1) + i, b = a + 1, c = a + GW + 1, d2 = c + 1;
    if (Math.max(Y[a], Y[b], Y[c], Y[d2]) <= 0) continue;
    if ((i + j) & 1) { tri(a, c, b, a * 2); tri(b, c, d2, a * 2 + 1); } else { tri(a, c, d2, a * 2); tri(a, d2, b, a * 2 + 1); }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geo.computeVertexNormals();
  const m = new THREE.Mesh(geo, std(0xffffff, {roughness: 1, metalness: 0, vertexColors: true, flatShading: true, map: caveRockTex()}));
  m.castShadow = true; m.receiveShadow = true;
  const hAt = (cx, cy) => { const i = Math.round((cx + 0.5 + B) * k), j = Math.round((cy + 0.5 + B) * k); return Math.max(0, Y[j * (GW + 1) + i]); };   // 칸 가운데의 바위 높이
  return {mesh: m, base: Float32Array.from(col), cells: Int32Array.from(cells), hAt};
}
let NEAR = 0;                                    // 0 = 멀리 (둥근 아이콘), 1 = 가까이 (도트 캐릭터)
let PERCEPT = 'all';                             // 지각 아이콘 표시: 'all' 전체 · 'sel' 선택하거나 가리킨 모험가만 · 'off' 끔
let ICONK = 1;                                   // 지각 아이콘 크기 (멀리서 보면 작게, 가까이서 1)
function lod(o) {
  const n = NEAR;
  o.token.visible = n < 0.999; o.token.material.opacity = (1 - n) * (o._fade ?? 1);
  o.pix.visible = n > 0.001; o.pix.material.opacity = n * (o._fade ?? 1);
  o.pix.material.alphaTest = n > 0.6 ? 0.5 : 0.01;
}

function makeToken(kind, team, size) {
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: tokenTex(kind, team), transparent: true, alphaTest: 0.05}));
  sp.center.set(0.5, 0.02);                       // 패의 아래 끝이 바닥에 닿는다
  sp.scale.set(size, size, 1);
  sp.renderOrder = 6;
  return sp;
}

function starTex() {
  if (_star) return _star;
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,240,1)'); gr.addColorStop(0.15, 'rgba(255,240,180,0.8)'); gr.addColorStop(1, 'rgba(255,220,120,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
  g.strokeStyle = 'rgba(255,255,230,0.9)'; g.lineWidth = 2;
  g.beginPath(); g.moveTo(32, 2); g.lineTo(32, 62); g.moveTo(2, 32); g.lineTo(62, 32); g.stroke();
  _star = new THREE.CanvasTexture(c); _star.colorSpace = THREE.SRGBColorSpace;
  return _star;
}
function holeTex() {
  if (_hole) return _hole;
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'), gr = g.createRadialGradient(64, 60, 0, 64, 64, 64);
  gr.addColorStop(0, '#000'); gr.addColorStop(0.62, '#020100'); gr.addColorStop(0.85, '#2a1b0e'); gr.addColorStop(1, 'rgba(60,42,24,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  _hole = new THREE.CanvasTexture(c); _hole.colorSpace = THREE.SRGBColorSpace;
  return _hole;
}

// ---------------- 캐릭터 ----------------
function makeChar(kind, team) {
  // 탐험가: 중절모를 쓴 남자 모험가 (곡괭이 · 횃불 · 금 가방). 궁수: 붉은 머리를 높이 묶은 여자 궁수 (활 · 화살통 · 망토)
  const T = TC[team], G = kind === 'G';
  const g = new THREE.Group(), body = new THREE.Group();
  g.add(body);
  const mTeam = std(T.c, {roughness: 0.55, emissive: T.c, emissiveIntensity: 0.1}), mDark = std(T.d, {roughness: 0.7, emissive: T.c, emissiveIntensity: 0.05});
  const mSkin = std(G ? 0xf2cbb0 : 0xd9a27a, {roughness: 0.6});
  const mShirt = std(G ? 0xe8dcc4 : 0xd8c8a0, {roughness: 0.85});           // 리넨 셔츠 · 블라우스
  const mMetal = std(0xb7c0cc, {metalness: 0.75, roughness: 0.28}), mWood = std(0x7a4f28, {roughness: 0.7}), mBlack = std(0x16181d, {roughness: 0.6});
  const mLeather = std(0x7a4c26, {roughness: 0.75}), mLeather2 = std(0x3c2514, {roughness: 0.8}), mGold = std(0xffc63a, {metalness: 0.8, roughness: 0.25, emissive: 0x6a4400, emissiveIntensity: 0.5});
  const mCloth = std(G ? 0x2b2833 : 0x9c865a, {roughness: 0.85}), mHair = std(G ? 0xd8a24a : 0x3b2414, {roughness: 0.5, emissive: G ? 0x3a2404 : 0x000000, emissiveIntensity: 0.35});
  const mWhite = std(0xf4f0ea, {roughness: 0.3}), mIris = std(G ? 0x2e8a52 : 0x3a6f9a, {roughness: 0.3}), mLip = std(0xc65a63, {roughness: 0.4});
  const RB = (w, h, d, r = 0.03) => new RoundedBoxGeometry(w, h, d, 2, r);
  const SP = (r, ws = 16, hs = 12) => new THREE.SphereGeometry(r, ws, hs);

  // ---- 다리: 바지 (궁수는 짙은 각반) + 긴 장화 ----
  const leg = (sx) => {
    const hip = new THREE.Group();
    hip.position.set(sx, 0.34, 0);
    body.add(hip);
    mesh(hip, RB(G ? 0.085 : 0.1, 0.2, G ? 0.095 : 0.11, 0.035), mCloth, 0, -0.1, 0);
    mesh(hip, RB(G ? 0.095 : 0.11, 0.16, G ? 0.12 : 0.13, 0.035), mLeather2, 0, -0.26, 0.01);
    mesh(hip, RB(G ? 0.1 : 0.115, 0.03, G ? 0.13 : 0.14, 0.01), mBlack, 0, -0.335, 0.02);
    mesh(hip, RB(G ? 0.1 : 0.115, 0.025, G ? 0.125 : 0.135, 0.01), mLeather, 0, -0.18, 0.01);     // 장화 접힌 테
    return hip;
  };
  const hipL = leg(G ? -0.065 : -0.08), hipR = leg(G ? 0.065 : 0.08);

  const pips = [], flames = [], quiver = [];
  let tail = null, dagger = null;
  if (!G) {
    // ---- 몸통: 팀 색 셔츠 + 가죽 조끼 + 벨트 + 가로지른 가방끈 ----
    mesh(body, RB(0.32, 0.29, 0.18, 0.07), mShirt, 0, 0.5, 0);
    mesh(body, new THREE.TorusGeometry(0.06, 0.026, 8, 18), mTeam, 0, 0.64, 0.01).rotation.x = Math.PI / 2 - 0.25;   // 팀 색 목수건
    const knot = mesh(body, new THREE.ConeGeometry(0.04, 0.09, 4), mTeam, 0.02, 0.58, 0.085); knot.rotation.set(0.3, 0, 3.0);
    for (const sx of [-1, 1]) mesh(body, RB(0.1, 0.27, 0.025, 0.012), mLeather, sx * 0.105, 0.5, 0.088);
    mesh(body, RB(0.3, 0.27, 0.025, 0.012), mLeather, 0, 0.5, -0.088);
    mesh(body, RB(0.07, 0.05, 0.02, 0.01), mShirt, 0, 0.6, 0.095);                // 열린 옷깃
    mesh(body, RB(0.33, 0.045, 0.19, 0.015), mLeather2, 0, 0.375, 0);
    mesh(body, RB(0.055, 0.04, 0.02, 0.008), mGold, 0, 0.375, 0.098);
    const strap = mesh(body, RB(0.035, 0.42, 0.02, 0.008), mLeather2, 0, 0.5, 0.1); strap.rotation.z = 0.72;
    const bag = new THREE.Group(); bag.position.set(0.18, 0.36, 0.05); body.add(bag);
    mesh(bag, RB(0.13, 0.12, 0.07, 0.025), mLeather, 0, 0, 0);
    mesh(bag, RB(0.135, 0.05, 0.075, 0.015), mLeather2, 0, 0.045, 0.004);
    const pm = std(0xffc63a, {emissive: 0xc98a00, emissiveIntensity: 1.2, metalness: 0.6, roughness: 0.3, flatShading: true});
    for (let i = 0; i < 5; i++) pips.push(mesh(bag, new THREE.DodecahedronGeometry(0.03), pm, -0.05 + i * 0.025, 0.085 + (i % 2) * 0.015, 0, false));
  } else {
    // ---- 몸통: 팀 색 윗옷 + 가죽 코르셋 + 치마 + 망토 + 화살통 ----
    mesh(body, RB(0.25, 0.22, 0.15, 0.065), mShirt, 0, 0.535, 0);
    mesh(body, RB(0.2, 0.16, 0.158, 0.05), mLeather, 0, 0.5, 0);                  // 가죽 조끼
    for (const sx of [-1, 1]) mesh(body, RB(0.03, 0.17, 0.162, 0.012), mTeam, sx * 0.06, 0.52, 0, false);   // 팀 색 끈
    mesh(body, RB(0.21, 0.1, 0.14, 0.04), mLeather, 0, 0.42, 0);
    for (const sy of [0.4, 0.44]) mesh(body, RB(0.215, 0.008, 0.145, 0.003), mGold, 0, sy, 0, false);
    mesh(body, new THREE.CylinderGeometry(0.115, 0.19, 0.17, 14, 1, true), std(T.c, {roughness: 0.65, emissive: T.c, emissiveIntensity: 0.08, side: THREE.DoubleSide}), 0, 0.3, 0);
    mesh(body, new THREE.TorusGeometry(0.19, 0.012, 6, 24), mDark, 0, 0.215, 0).rotation.x = Math.PI / 2;
    mesh(body, RB(0.09, 0.04, 0.12, 0.02), mLeather2, -0.15, 0.625, 0);           // 어깨 가죽
    const cape = mesh(body, new THREE.PlaneGeometry(0.3, 0.48, 1, 4), std(T.d, {roughness: 0.8, side: THREE.DoubleSide, emissive: T.c, emissiveIntensity: 0.08}), 0, 0.4, -0.1);
    cape.rotation.x = 0.16;
    mesh(body, new THREE.TorusGeometry(0.07, 0.022, 8, 18), mDark, 0, 0.655, -0.01).rotation.x = Math.PI / 2;   // 망토 깃
    const qv = new THREE.Group(); qv.position.set(0.07, 0.52, -0.13); qv.rotation.z = -0.4; body.add(qv);
    mesh(qv, new THREE.CylinderGeometry(0.048, 0.042, 0.3, 12), mLeather, 0, 0, 0);
    mesh(qv, new THREE.TorusGeometry(0.048, 0.01, 6, 14), mGold, 0, 0.15, 0).rotation.x = Math.PI / 2;
    for (let i = 0; i < 3; i++) {
      const f = new THREE.Group();
      f.position.set((i - 1) * 0.022, 0.17, (i % 2) * 0.015);
      qv.add(f);
      mesh(f, new THREE.CylinderGeometry(0.005, 0.005, 0.12, 5), mWood, 0, -0.02, 0, false);
      const fl = mesh(f, new THREE.ConeGeometry(0.022, 0.07, 4), std(T.l, {emissive: T.c, emissiveIntensity: 0.4}), 0, 0.06, 0, false);
      fl.rotation.y = Math.PI / 4;
      quiver.push(f);
    }
  }

  // ---- 목과 머리 ----
  mesh(body, new THREE.CylinderGeometry(0.042, 0.05, 0.07, 12), mSkin, 0, 0.665, 0);
  const head = new THREE.Group();
  head.position.set(0, 0.79, 0);
  body.add(head);
  mesh(head, SP(0.125, 28, 20), mSkin, 0, 0, 0).scale.set(0.94, 1.04, 0.98);
  mesh(head, SP(G ? 0.085 : 0.1, 20, 14), mSkin, 0, -0.05, 0.025).scale.set(G ? 0.95 : 1.05, 0.78, 0.95);   // 턱
  for (const sx of [-1, 1]) mesh(head, SP(0.026, 10, 8), mSkin, sx * 0.118, -0.005, -0.005).scale.set(0.5, 1, 0.8);   // 귀
  mesh(head, SP(0.021, 10, 8), mSkin, 0, -0.012, 0.122, false).scale.set(0.85, 1.05, 1.1);                  // 코
  for (const sx of [-1, 1]) {                                                                                  // 눈
    mesh(head, SP(0.026, 14, 10), mWhite, sx * 0.046, 0.022, 0.104, false).scale.set(1.25, G ? 0.95 : 0.8, 0.5);
    mesh(head, SP(0.016, 12, 10), mIris, sx * 0.046, 0.021, 0.116, false).scale.set(1, 1, 0.5);
    mesh(head, SP(0.008, 8, 6), mBlack, sx * 0.046, 0.021, 0.122, false);
    mesh(head, SP(0.0045, 6, 4), mWhite, sx * 0.046 + 0.006, 0.028, 0.125, false);
    const brow = mesh(head, RB(G ? 0.046 : 0.054, G ? 0.009 : 0.014, 0.012, 0.004), mHair, sx * 0.047, 0.06, 0.111, false);
    brow.rotation.z = G ? -sx * 0.18 : sx * 0.08;
  }
  if (G) {
    for (const sx of [-1, 1]) {                                                                                // 속눈썹 · 볼 · 입술
      const l = mesh(head, RB(0.02, 0.007, 0.006, 0.002), mBlack, sx * 0.072, 0.036, 0.1, false); l.rotation.z = -sx * 0.5;
      mesh(head, SP(0.022, 10, 8), std(0xf3a5a0, {roughness: 0.6, transparent: true, opacity: 0.55}), sx * 0.07, -0.018, 0.098, false).scale.set(1.1, 0.55, 0.3);
    }
    mesh(head, SP(0.017, 12, 8), mLip, 0, -0.058, 0.108, false).scale.set(1.55, 0.5, 0.6);
    // 머리카락: 앞머리 · 옆머리 · 높이 묶은 꼬리머리
    mesh(head, new THREE.SphereGeometry(0.136, 26, 16, 0, Math.PI * 2, 0, Math.PI * 0.56), mHair, 0, 0.008, -0.004);
    mesh(head, new THREE.SphereGeometry(0.138, 22, 8, Math.PI * 0.12, Math.PI * 0.76, Math.PI * 0.1, Math.PI * 0.2), mHair, 0, 0.004, 0);
    for (const sx of [-1, 1]) { const s2 = mesh(head, RB(0.04, 0.17, 0.07, 0.02), mHair, sx * 0.112, -0.05, 0.02); s2.rotation.z = sx * 0.12; }
    tail = new THREE.Group(); tail.position.set(0, 0.09, -0.11); head.add(tail);
    mesh(tail, new THREE.TorusGeometry(0.028, 0.012, 6, 14), mTeam, 0, 0, 0).rotation.x = 0.4;
    for (let k = 0; k < 5; k++) mesh(tail, SP(0.05 - k * 0.006, 12, 10), mHair, 0, -0.03 - k * 0.055, -0.03 - k * 0.012).scale.set(0.9, 1.25, 0.9);
  } else {
    mesh(head, RB(0.044, 0.008, 0.01, 0.003), std(0x8a4a3a), 0, -0.062, 0.113, false);                      // 입
    mesh(head, new THREE.SphereGeometry(0.104, 20, 10, 0, Math.PI, Math.PI * 0.52, Math.PI * 0.4),           // 수염 자국
      std(0x2a1a10, {roughness: 0.9, transparent: true, opacity: 0.42}), 0, -0.03, 0.03, false);
    mesh(head, new THREE.SphereGeometry(0.131, 22, 14, 0, Math.PI * 2, 0, Math.PI * 0.5), mHair, 0, 0.006, -0.008);
    for (const sx of [-1, 1]) mesh(head, RB(0.02, 0.06, 0.04, 0.01), mHair, sx * 0.115, -0.015, 0.03);       // 구레나룻
    const hat = new THREE.Group(); hat.position.set(0, 0.1, -0.005); hat.rotation.set(-0.1, 0, 0.06); head.add(hat);
    mesh(hat, new THREE.CylinderGeometry(0.225, 0.235, 0.016, 32), mLeather, 0, 0, 0);
    mesh(hat, new THREE.CylinderGeometry(0.105, 0.13, 0.12, 24), mLeather, 0, 0.066, 0);
    mesh(hat, new THREE.CylinderGeometry(0.132, 0.132, 0.032, 24), mTeam, 0, 0.025, 0);
    mesh(hat, RB(0.05, 0.02, 0.15, 0.01), mLeather2, 0, 0.125, 0, false);                                     // 모자 위 홈
  }

  // ---- 팔 ----
  const arm = (sx) => {
    const sh = new THREE.Group();
    sh.position.set(sx, 0.615, 0);
    body.add(sh);
    mesh(sh, SP(G ? 0.042 : 0.05, 12, 10), G ? mTeam : mLeather, 0, -0.01, 0);
    mesh(sh, RB(G ? 0.062 : 0.078, 0.15, G ? 0.062 : 0.078, 0.028), mShirt, 0, -0.08, 0);
    mesh(sh, RB(G ? 0.056 : 0.068, 0.13, G ? 0.056 : 0.068, 0.025), G ? mLeather : mSkin, 0, -0.205, 0);    // 팔뚝 (궁수는 가죽 팔찌)
    mesh(sh, SP(G ? 0.036 : 0.042, 12, 10), mSkin, 0, -0.285, 0);
    const hand = new THREE.Group();
    hand.position.set(0, -0.285, 0);
    sh.add(hand);
    return {sh, hand};
  };
  const L = arm(G ? -0.155 : -0.19), Rr = arm(G ? 0.155 : 0.19);
  if (!G) {           // 곡괭이와 횃불
    const handle = mesh(Rr.hand, new THREE.CylinderGeometry(0.017, 0.017, 0.46, 8), mWood, 0, 0, 0.18);
    handle.rotation.x = Math.PI / 2;
    const pk = new THREE.Group(); pk.position.set(0, 0, 0.39); Rr.hand.add(pk);
    for (const sx of [-1, 1]) { const tip = mesh(pk, new THREE.ConeGeometry(0.026, 0.17, 8), mMetal, sx * 0.085, -0.012, 0); tip.rotation.z = sx * -1.75; }
    mesh(pk, RB(0.06, 0.05, 0.05, 0.01), mMetal, 0, 0, 0);
    const stick = mesh(L.hand, new THREE.CylinderGeometry(0.018, 0.014, 0.3, 8), mWood, 0, 0.1, 0.05);
    stick.rotation.x = 0.35;
    mesh(L.hand, new THREE.CylinderGeometry(0.03, 0.022, 0.05, 10), mLeather2, 0, 0.24, 0.1);
    const fl = new THREE.Group();
    fl.position.set(0, 0.28, 0.11);
    L.hand.add(fl);
    mesh(fl, new THREE.ConeGeometry(0.05, 0.16, 10), new THREE.MeshBasicMaterial({color: 0xffa040}), 0, 0.06, 0, false);
    mesh(fl, new THREE.ConeGeometry(0.028, 0.1, 8), new THREE.MeshBasicMaterial({color: 0xfff0a0}), 0, 0.035, 0, false);
    flames.push(fl);
  } else {            // 뒤로 휜 활 (금빛 끝)
    const bow = new THREE.Group();
    bow.position.set(0, 0, 0.05);
    L.hand.add(bow);
    const limb = mesh(bow, new THREE.TorusGeometry(0.3, 0.017, 8, 30, Math.PI * 0.86), mWood, 0, 0, 0);
    limb.rotation.set(0, Math.PI / 2, Math.PI / 2 - Math.PI * 0.43);
    for (const sy of [-1, 1]) mesh(bow, SP(0.022, 8, 6), mGold, 0, sy * 0.29, -0.085, false);
    mesh(bow, new THREE.CylinderGeometry(0.0035, 0.0035, 0.58, 4), std(0xf2ead8), 0, 0, -0.088, false);
    mesh(L.hand, new THREE.CylinderGeometry(0.024, 0.024, 0.08, 8), mLeather2, 0, 0, 0.05);
    dagger = new THREE.Group(); dagger.position.set(0, -0.02, 0.03); dagger.rotation.x = Math.PI / 2; Rr.hand.add(dagger);
    mesh(dagger, new THREE.CylinderGeometry(0.014, 0.014, 0.07, 6), mLeather2, 0, -0.03, 0, false);
    mesh(dagger, RB(0.07, 0.012, 0.02, 0.005), mGold, 0, 0.01, 0, false);
    const bl = mesh(dagger, new THREE.ConeGeometry(0.022, 0.18, 4), std(0xe6eef8, {metalness: 0.9, roughness: 0.15, emissive: 0x334455, emissiveIntensity: 0.4}), 0, 0.11, 0, false);
    bl.scale.z = 0.3;
    dagger.visible = false;
  }
  const hp = hpBar(0.6);
  hp.position.y = 1.08;
  g.add(hp);
  const seg = G ? 6 : 32;
  const disc = new THREE.Group();
  const fillD = new THREE.Mesh(new THREE.CircleGeometry(0.36, seg).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: T.c, transparent: true, opacity: 0.28, depthWrite: false}));
  const rimD = new THREE.Mesh(new THREE.RingGeometry(0.33, 0.4, seg).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: T.c, transparent: true, opacity: 0.95, depthWrite: false}));
  if (G) { fillD.rotation.y = rimD.rotation.y = Math.PI / 6; }
  disc.add(fillD, rimD); disc.position.y = 0.015; disc.renderOrder = 4;
  g.add(disc);
  const badge = new THREE.Sprite(new THREE.SpriteMaterial({map: badgeTex(kind, team), color: 0xb4b4b4, transparent: true, depthTest: false, sizeAttenuation: false}));
  badge.position.y = 1.3; badge.scale.set(0.027, 0.027, 1); badge.renderOrder = 15;      // 화면에서 늘 같은 크기
  g.add(badge);
  g.traverse(o => { if (o.isMesh && o.castShadow) o.receiveShadow = true; });
  for (const m of [mTeam, mDark, mSkin]) m.userData.base = m.emissive.clone();
  for (const ch of body.children) ch.visible = false;
  const token = makeToken(kind, team, G ? 0.62 : 0.68);
  body.add(token);
  const shadow = makeShadow(0.5, 0.3); g.add(shadow);
  const pool = new THREE.Mesh(shadowG, new THREE.MeshBasicMaterial({map: softTex(), color: 0xffc070, transparent: true, opacity: 0.85, depthWrite: false, blending: THREE.AdditiveBlending}));
  pool.scale.set(1.0, 1, 1.0); pool.position.y = 0.008; pool.renderOrder = 2; pool.visible = false; g.add(pool);   // 시안 3: 자기 칸만 비추는 등불
  const icons = [];
  for (let k = 0; k < 6; k++) { const ic = new THREE.Sprite(new THREE.SpriteMaterial({transparent: true, depthTest: false})); ic.scale.set(0.2, 0.2, 1); ic.renderOrder = 16; ic.visible = false; body.add(ic); icons.push(ic); }
  const pix = makeBody(kind, team, 0.6);
  body.add(pix);
  const glow = pix.userData.lpc ? lpcSprite(sheetName(kind, team), pix.userData.w, true)
    : new THREE.Sprite(new THREE.SpriteMaterial({map: glowTex(kind, team, 0), transparent: true, depthTest: false, blending: THREE.AdditiveBlending}));
  glow.center.copy(pix.center); glow.scale.copy(pix.scale); glow.renderOrder = 12; glow.visible = false; body.add(glow);
  const bar = new THREE.Sprite(new THREE.SpriteMaterial({map: hpTex(10, team), transparent: true, depthTest: false}));
  bar.scale.set(0.36, 0.063, 1); bar.renderOrder = 14; body.add(bar);
  badge.visible = false;
  return {g, shadow, pool, icons, token, pix, glow, bar, body, hipL, hipR, shL: L.sh, shR: Rr.sh, head, tail, dagger, pips, flames, quiver, hp, disc, badge, flash: [mTeam, mDark, mSkin], kind, team, face: null, x: 0, y: 0};
}

function setFlash(o, k) {
  if (o._flash === k) return;
  o._flash = k;
  if (o.token) { o.token.material.color.setRGB(1, 1 - k * 0.65, 1 - k * 0.65); o.pix.material.color.setRGB(1, 1 - k * 0.65, 1 - k * 0.65); }
  for (const m of o.flash) m.emissive.copy(m.userData.base).lerp(HITC, k);
}

function pose(o, st, a, now, id) {
  const {body, hipL, hipR, shL, shR} = o;
  hipL.rotation.set(0, 0, 0); hipR.rotation.set(0, 0, 0);
  shL.rotation.set(0, 0, 0); shR.rotation.set(0, 0, 0);
  body.position.set(0, 0, 0); body.rotation.set(0, 0, 0);
  if (o.kind === 'G') shL.rotation.x = -0.35;                    // 활을 낮게
  else shL.rotation.x = -0.6;                                    // 횃불을 앞으로
  if (st === 'walk') {
    const ph = a * Math.PI * 2, s = Math.sin(ph);
    hipL.rotation.x = s * 0.75; hipR.rotation.x = -s * 0.75;
    shL.rotation.x += -s * 0.55; shR.rotation.x = s * 0.55;
    body.position.y = Math.abs(Math.cos(ph)) * 0.05;
    body.rotation.x = 0.08;
  } else if (st === 'mine') {
    let t;
    if (a < 0.45) t = -2.7 * easeOut(a / 0.45);
    else if (a < 0.58) t = -2.7 + 2.3 * ((a - 0.45) / 0.13);
    else t = -0.4 * (1 - (a - 0.58) / 0.42);
    shR.rotation.x = t; shL.rotation.x = t * 0.8;
    body.rotation.x = a > 0.45 && a < 0.8 ? 0.22 : 0.05;
    hipL.rotation.x = 0.2; hipR.rotation.x = -0.25;
  } else if (st === 'attack') {
    const aim = a < 0.7 ? Math.min(1, a / 0.15) : 1 - (a - 0.7) / 0.3;
    shL.rotation.x = -1.5 * aim - 0.35 * (1 - aim);
    const draw = a < 0.18 ? a / 0.18 : a < 0.28 ? 1 : Math.max(0, 1 - (a - 0.28) / 0.1);
    shR.rotation.x = -1.45 * aim; shR.rotation.y = 0.9 * draw;
    body.rotation.y = -0.25 * aim;
    body.position.z = a > 0.28 && a < 0.45 ? -0.04 : 0;
    hipL.rotation.x = 0.3; hipR.rotation.x = -0.25;
  } else if (st === 'push') {                                     // 두 손으로 확 민다
    const k = Math.sin(Math.PI * Math.min(1, a / 0.55));
    shL.rotation.x = -1.55 * k - 0.3 * (1 - k); shR.rotation.x = -1.55 * k;
    body.position.z = 0.12 * k; body.rotation.x = 0.25 * k;
    hipL.rotation.x = 0.45 * k; hipR.rotation.x = -0.35 * k;
  } else if (st === 'stagger') {                                  // 밀려서 뒤로 휘청
    const k = Math.sin(Math.PI * Math.min(1, a));
    body.rotation.x = -0.45 * k; shL.rotation.x = -2.2 * k; shR.rotation.x = -2.2 * k;
    shL.rotation.z = 0.4 * k; shR.rotation.z = -0.4 * k;
    hipL.rotation.x = -0.4 * k; hipR.rotation.x = 0.3 * k;
  } else {                                                        // 숨쉬기
    const b = Math.sin(now * 2.2 + id);
    body.position.y = b * 0.012;
    shL.rotation.z += 0.05 + b * 0.03; shR.rotation.z = -0.05 - b * 0.03;
  }
  if (o.head) o.head.rotation.set(st === 'attack' ? -0.05 : Math.sin(now * 0.7 + id) * 0.05, st === 'idle' ? Math.sin(now * 0.45 + id * 1.3) * 0.35 : 0, 0);
  if (o.tail) o.tail.rotation.x = 0.2 + Math.sin(now * 2.6 + id) * 0.07 + (st === 'walk' ? Math.abs(Math.sin(a * Math.PI * 2)) * 0.35 : 0) + (st === 'stagger' ? 0.6 : 0);
}

// ---------------- 야영지 ----------------
function makeBase(t) {
  const T = TC[t], g = new THREE.Group();
  const stone = std(0x6b5a44, {roughness: 0.9}), cloth = std(T.c, {roughness: 0.75, side: THREE.DoubleSide}), dark = std(T.d, {roughness: 0.8});
  const wood = std(0x6a4522, {roughness: 0.85});
  mesh(g, new THREE.CylinderGeometry(0.5, 0.54, 0.08, 18), stone, 0, 0.04, 0);
  const tent = mesh(g, new THREE.ConeGeometry(0.42, 0.78, 4, 1, true), cloth, 0, 0.47, 0);
  tent.rotation.y = Math.PI / 4;
  mesh(g, new THREE.ConeGeometry(0.43, 0.2, 4, 1, true), dark, 0, 0.77, 0).rotation.y = Math.PI / 4;
  mesh(g, new THREE.PlaneGeometry(0.2, 0.32), std(0x120b05), 0, 0.24, 0.21, false).rotation.x = -0.5;
  mesh(g, new THREE.CylinderGeometry(0.014, 0.014, 0.5, 6), wood, 0, 1.0, 0);
  const flag = new THREE.Group();
  flag.position.set(0, 1.18, 0);
  g.add(flag);
  mesh(flag, new THREE.PlaneGeometry(0.3, 0.17), new THREE.MeshStandardMaterial({color: T.l, side: THREE.DoubleSide, emissive: T.c, emissiveIntensity: 0.35}), 0.15, 0, 0);
  // 모닥불
  const fire = new THREE.Group();
  fire.position.set(0.36, 0.08, 0.36);
  g.add(fire);
  for (let i = 0; i < 3; i++) { const l = mesh(fire, new THREE.CylinderGeometry(0.025, 0.025, 0.24, 6), wood, 0, 0.03, 0); l.rotation.set(Math.PI / 2, i * 1.05, 0); }
  for (let i = 0; i < 6; i++) mesh(fire, new THREE.DodecahedronGeometry(0.04), stone, Math.cos(i) * 0.13, 0.02, Math.sin(i) * 0.13);
  const core = new THREE.Group();
  fire.add(core);
  mesh(core, new THREE.ConeGeometry(0.08, 0.26, 10), new THREE.MeshBasicMaterial({color: 0xff7a1a}), 0, 0.16, 0, false);
  mesh(core, new THREE.ConeGeometry(0.05, 0.18, 8), new THREE.MeshBasicMaterial({color: 0xffe08a}), 0, 0.13, 0, false);
  const light = new THREE.PointLight(0xff9a40, 3, 4.5, 1.6);
  light.position.set(0, 0.35, 0);
  fire.add(light);
  // 금 더미
  const gm = std(0xffc63a, {emissive: 0x9a6400, emissiveIntensity: 0.8, metalness: 0.6, roughness: 0.3, flatShading: true});
  const pile = new THREE.Group();
  pile.position.set(-0.36, 0.08, 0.3);
  g.add(pile);
  for (let i = 0; i < 6; i++) mesh(pile, new THREE.DodecahedronGeometry(0.05), gm, (i % 3 - 1) * 0.06, 0.04 + Math.floor(i / 3) * 0.06, (i % 2) * 0.05, false);
  mesh(g, new THREE.BoxGeometry(0.16, 0.14, 0.16), wood, -0.38, 0.15, -0.3);
  // 나무 울타리 (앞쪽은 드나드는 문으로 비움)
  for (let i = 0; i < 16; i++) {
    const a = i / 16 * Math.PI * 2;
    if (Math.abs(Math.atan2(Math.sin(a), Math.cos(a)) - Math.PI / 2) < 0.45) continue;
    const r = 0.56, h = 0.26 + (i % 3) * 0.04;
    mesh(g, new THREE.CylinderGeometry(0.028, 0.032, h, 6), wood, Math.cos(a) * r, h / 2 + 0.06, Math.sin(a) * r);
    mesh(g, new THREE.ConeGeometry(0.03, 0.07, 6), wood, Math.cos(a) * r, h + 0.095, Math.sin(a) * r);
  }
  // 문 양쪽의 횃대
  for (const sx of [-0.2, 0.2]) {
    mesh(g, new THREE.CylinderGeometry(0.02, 0.025, 0.5, 6), wood, sx, 0.31, 0.56);
    mesh(g, new THREE.ConeGeometry(0.045, 0.13, 8), new THREE.MeshBasicMaterial({color: 0xff8a2a}), sx, 0.62, 0.56, false);
  }
  // 팀 깃발 두 개 더
  for (const sx of [-0.45, 0.45]) {
    mesh(g, new THREE.CylinderGeometry(0.012, 0.012, 0.7, 6), wood, sx, 0.41, -0.42);
    mesh(g, new THREE.PlaneGeometry(0.16, 0.24), new THREE.MeshStandardMaterial({color: T.c, side: THREE.DoubleSide, emissive: T.c, emissiveIntensity: 0.25}), sx + 0.08, 0.64, -0.42);
  }
  const hp = hpBar(1.0);
  hp.position.y = 1.55;
  g.add(hp);
  g.traverse(o => { if (o.isMesh) o.receiveShadow = true; });
  for (const ch of g.children) if (ch !== hp) ch.traverse(o => { if (o.isMesh) o.visible = false; });
  const CS = SHEETS['camp_' + t];
  let spr;
  if (CS) {                                     // LPC 야영지 시트 (천막 · 팀 깃발 · 모닥불)
    const tx = CS.tex.clone(); tx.repeat.set(1 / CS.m.cols, 1); tx.needsUpdate = true;
    spr = new THREE.Sprite(new THREE.SpriteMaterial({map: tx, transparent: true, alphaTest: 0.5}));
    spr.center.set(0.5, (CS.m.cell - CS.m.foot) / CS.m.cell); spr.scale.set(1.55, 1.55, 1); spr.renderOrder = 5;
    spr.userData.camp = CS.m;
  } else spr = pxSprite(campTex(t, false, 0), 1.35, 1.35, 0.1);
  g.add(spr);
  return {g, spr, core, flag, fire, light, tent, pile, hp, flash: [stone, cloth], team: t};
}

// ---------------- 웜퍼스 ----------------
function makeWumpus() {
  const g = new THREE.Group(), live = new THREE.Group(), dead = new THREE.Group();
  g.add(live, dead);
  const fur = std(0x6d8a3a, {roughness: 0.9, flatShading: true, emissive: 0x1e3208, emissiveIntensity: 0.6}), fur2 = std(0x435a22, {roughness: 1, flatShading: true, emissive: 0x142206, emissiveIntensity: 0.5});
  const belly = std(0xa89c5a, {roughness: 0.85, flatShading: true, emissive: 0x2a2408, emissiveIntensity: 0.4}), bone = std(0xe4dcc2, {roughness: 0.6}), horn = std(0xd9cfae, {roughness: 0.45});
  const gum = std(0x5a1410, {roughness: 0.6}), eyeM = new THREE.MeshBasicMaterial({color: 0xd8ff40});
  // 굴: 검은 바닥과 둘레의 뼈
  const den = mesh(g, new THREE.CircleGeometry(0.62, 28).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: 0x050703, transparent: true, opacity: 0.8, depthWrite: false}), 0, 0.012, 0, false);
  den.renderOrder = 1;
  const aura = mesh(g, new THREE.PlaneGeometry(2.2, 2.2).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({map: softTex(), color: 0x8fff3a, transparent: true, opacity: 0.5, depthWrite: false, blending: THREE.AdditiveBlending}), 0, 0.03, 0, false);
  aura.renderOrder = 2;
  for (let i = 0; i < 7; i++) {
    const a = i / 7 * Math.PI * 2 + 0.3, b = new THREE.Group();
    b.position.set(Math.cos(a) * 0.5, 0.03, Math.sin(a) * 0.5); b.rotation.set(Math.PI / 2, 0, a + 1.2 + hash(i, 2));
    g.add(b);
    mesh(b, new THREE.CylinderGeometry(0.016, 0.016, 0.24, 6), bone, 0, 0, 0);
    for (const e of [-0.12, 0.12]) mesh(b, new THREE.SphereGeometry(0.028, 8, 6), bone, 0, e, 0);
  }
  // 몸: 털북숭이 덩치
  const body = new THREE.Group();
  live.add(body);
  const torso = mesh(body, new THREE.IcosahedronGeometry(0.42, 1), fur, 0, 0.44, 0); torso.scale.set(1.12, 0.98, 1.0);
  mesh(body, new THREE.IcosahedronGeometry(0.3, 1), belly, 0, 0.38, 0.2).scale.set(0.95, 0.9, 0.5);
  for (let i = 0; i < 18; i++) {                 // 등의 털 가시
    const a = hash(i, 3) * Math.PI * 1.6 + Math.PI * 0.7, el = 0.2 + hash(i, 5) * 0.9;
    const sp = mesh(body, new THREE.ConeGeometry(0.055, 0.24, 5), fur2, Math.cos(a) * Math.cos(el) * 0.4, 0.44 + Math.sin(el) * 0.38, Math.sin(a) * Math.cos(el) * 0.36);
    sp.lookAt(sp.position.x * 3, sp.position.y * 3 - 0.9, sp.position.z * 3); sp.rotateX(Math.PI / 2);
  }
  for (const sx of [-1, 1]) {                     // 짧은 다리
    mesh(body, new THREE.CylinderGeometry(0.11, 0.13, 0.22, 8), fur2, sx * 0.2, 0.1, 0);
    for (let k = -1; k <= 1; k++) { const c = mesh(body, new THREE.ConeGeometry(0.025, 0.08, 5), horn, sx * 0.2 + k * 0.05, 0.03, 0.13); c.rotation.x = Math.PI / 2; }
  }
  const arms = [];
  for (const sx of [-1, 1]) {                     // 긴 팔과 발톱
    const sh = new THREE.Group();
    sh.position.set(sx * 0.42, 0.6, 0.08); body.add(sh);
    mesh(sh, new THREE.CylinderGeometry(0.075, 0.09, 0.42, 7), fur, 0, -0.2, 0);
    const hand = new THREE.Group(); hand.position.y = -0.42; sh.add(hand);
    mesh(hand, new THREE.IcosahedronGeometry(0.09, 0), fur2, 0, 0, 0);
    for (let k = -1; k <= 1; k++) { const c = mesh(hand, new THREE.ConeGeometry(0.024, 0.14, 5), horn, k * 0.045, -0.04, 0.08); c.rotation.x = 1.9; }
    sh.rotation.z = sx * 0.25; arms.push(sh);
  }
  // 머리
  const head = new THREE.Group();
  head.position.set(0, 0.8, 0.3); head.scale.setScalar(1.3); body.add(head);
  mesh(head, new THREE.IcosahedronGeometry(0.25, 1), fur, 0, 0, 0).scale.set(1.15, 0.92, 1.05);
  mesh(head, new THREE.IcosahedronGeometry(0.14, 1), belly, 0, -0.06, 0.18).scale.set(1.2, 0.7, 0.8);       // 주둥이
  const eyes = [];
  for (const sx of [-1, 1]) {
    const e = mesh(head, new THREE.SphereGeometry(0.06, 12, 10), eyeM, sx * 0.1, 0.06, 0.21, false); e.scale.set(1.3, 0.75, 0.6); eyes.push(e);
    mesh(head, new THREE.BoxGeometry(0.11, 0.025, 0.04), fur2, sx * 0.1, 0.12, 0.2, false).rotation.z = -sx * 0.35;   // 성난 눈썹
    const h1 = new THREE.Group(); h1.position.set(sx * 0.17, 0.14, -0.02); h1.rotation.set(-0.3, 0, -sx * 0.7); head.add(h1);
    mesh(h1, new THREE.ConeGeometry(0.055, 0.22, 8), horn, 0, 0.1, 0);
    const h2 = mesh(h1, new THREE.ConeGeometry(0.035, 0.16, 8), horn, 0, 0.24, -0.04); h2.rotation.x = -0.7;
  }
  const jaw = new THREE.Group();
  jaw.position.set(0, -0.12, 0.12); head.add(jaw);
  mesh(jaw, new THREE.BoxGeometry(0.28, 0.06, 0.2), fur2, 0, -0.03, 0.06);
  mesh(jaw, new THREE.BoxGeometry(0.24, 0.02, 0.16), gum, 0, 0.005, 0.06, false);
  for (let k = 0; k < 5; k++) { const t = mesh(jaw, new THREE.ConeGeometry(0.018, 0.06, 4), bone, -0.09 + k * 0.045, 0.03, 0.14, false); }
  for (let k = 0; k < 4; k++) { const t = mesh(head, new THREE.ConeGeometry(0.02, 0.07, 4), bone, -0.07 + k * 0.047, -0.1, 0.25, false); t.rotation.x = Math.PI; }
  const eyeL = new THREE.PointLight(0xc8ff40, 3, 3.5, 1.4); eyeL.position.set(0, 0.85, 0.55); live.add(eyeL);
  // 쓰러진 모습: 해골과 갈비뼈
  const sk = mesh(dead, new THREE.IcosahedronGeometry(0.2, 1), bone, 0.05, 0.16, 0.18); sk.scale.set(1.1, 0.85, 1.05);
  for (const sx of [-1, 1]) {
    mesh(dead, new THREE.SphereGeometry(0.05, 10, 8), std(0x140e08), 0.05 + sx * 0.08, 0.2, 0.36, false).scale.set(1, 0.8, 0.4);
    const h1 = mesh(dead, new THREE.ConeGeometry(0.05, 0.3, 8), horn, 0.05 + sx * 0.2, 0.2, 0.12); h1.rotation.set(0.2, 0, -sx * 1.2);
  }
  for (let k = 0; k < 5; k++) {
    const r = mesh(dead, new THREE.TorusGeometry(0.2 - k * 0.015, 0.018, 5, 14, Math.PI), bone, -0.1, 0.06, -0.12 - k * 0.07);
    r.rotation.set(0, Math.PI / 2, 0.2);
  }
  mesh(dead, new THREE.CylinderGeometry(0.025, 0.025, 0.5, 6), bone, -0.1, 0.05, -0.25).rotation.x = Math.PI / 2;
  dead.visible = false;
  const hp = hpBar(0.9);
  hp.position.y = 1.65;
  g.add(hp);
  g.traverse(o => { if (o.isMesh) o.castShadow = true; });
  for (const m of [fur, fur2, belly]) m.userData.base = m.emissive.clone();
  for (const ch of body.children) ch.visible = false;
  const token = makeToken('W', -1, 0.95);
  body.add(token);
  const pix = makeBody('W', -1, 0.72);
  body.add(pix);
  for (const ch of g.children) if (ch.isGroup && ch !== live && ch !== dead && ch !== hp) ch.visible = false;
  dead.traverse(o => { if (o.isMesh) o.visible = false; });
  const dsp = makeBody('W', -1, 0.75);
  if (dsp.userData.lpc) lpcFrame(dsp, 'hurt', 0, 99); else dsp.material.map = bodyTex('W', -1, 9);
  dead.add(dsp);
  const wsh = makeShadow(0.75, 0.42); live.add(wsh);
  const bones = frameSprite('bones', 0, 0.55, 0.55, 2 / 32); if (bones) { bones.position.set(-0.22, 0, 0.12); dead.add(bones); }
  return {g, den, wsh, token, pix, live, dead, body, head, jaw, eyes, eyeL, arms, hp, aura, flash: [fur, fur2, belly]};
}

function makeLoot() {
  const g = new THREE.Group(), sack = new THREE.Group(), chest = new THREE.Group();
  g.add(sack, chest);
  const leather = std(0x8a5a2a, {roughness: 0.85}), gold = std(0xffc63a, {emissive: 0xc98a00, emissiveIntensity: 0.9, metalness: 0.7, roughness: 0.25});
  const wood = std(0x5a3414, {roughness: 0.8}), iron = std(0x3a3a3e, {metalness: 0.6, roughness: 0.4});
  const glow = mesh(g, new THREE.PlaneGeometry(1.2, 1.2).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({map: softTex(), color: 0xffc040, transparent: true, opacity: 0.5, depthWrite: false, blending: THREE.AdditiveBlending}), 0, 0.02, 0, false);
  glow.renderOrder = 1;
  mesh(sack, new THREE.SphereGeometry(0.18, 14, 12), leather, 0, 0.16, 0).scale.set(1, 0.88, 1);
  mesh(sack, new THREE.CylinderGeometry(0.06, 0.1, 0.1, 10), leather, 0, 0.32, 0);
  mesh(sack, new THREE.TorusGeometry(0.065, 0.014, 6, 14), gold, 0, 0.32, 0).rotation.x = Math.PI / 2;
  mesh(sack, new THREE.ConeGeometry(0.08, 0.08, 8), leather, 0, 0.4, 0).rotation.x = Math.PI;
  mesh(chest, new THREE.BoxGeometry(0.5, 0.26, 0.34), wood, 0, 0.14, 0);
  const lid = mesh(chest, new THREE.CylinderGeometry(0.17, 0.17, 0.5, 14, 1, false, 0, Math.PI), wood, 0, 0.27, 0); lid.rotation.set(0, 0, Math.PI / 2); lid.rotation.y = Math.PI / 2;
  for (const sx of [-0.18, 0.18]) mesh(chest, new THREE.BoxGeometry(0.04, 0.3, 0.36), iron, sx, 0.16, 0);
  mesh(chest, new THREE.BoxGeometry(0.08, 0.1, 0.03), gold, 0, 0.2, 0.18);
  for (let k = 0; k < 7; k++) mesh(chest, new THREE.DodecahedronGeometry(0.05), gold, (hash(k, 1) - 0.5) * 0.36, 0.3 + hash(k, 2) * 0.05, (hash(k, 3) - 0.5) * 0.2, false);
  const coins = [];
  for (let k = 0; k < 6; k++) {
    const c = mesh(g, new THREE.CylinderGeometry(0.055, 0.055, 0.015, 12), gold, Math.cos(k * 1.1) * (0.22 + hash(k, 7) * 0.1), 0.01, Math.sin(k * 1.1) * (0.22 + hash(k, 7) * 0.1), false);
    c.rotation.set(hash(k, 9) * 0.5, 0, hash(k, 11) * 0.5); coins.push(c);
  }
  const lbl = new THREE.Sprite(new THREE.SpriteMaterial({transparent: true, depthTest: false, sizeAttenuation: false}));
  lbl.position.set(0, 0.75, 0); lbl.scale.set(0.045, 0.0235, 1); lbl.renderOrder = 14;
  g.add(lbl);
  g.traverse(o => { if (o.isMesh && o !== glow) o.visible = false; });
  const ss = frameSprite('loot', 0, 0.62, 0.62, 2 / 32), cs2 = frameSprite('loot', 2, 0.72, 0.72, 2 / 32);
  sack.add(ss || pxSprite(lootTex(false), 0.5, 0.5, 0.05));
  chest.add(cs2 || pxSprite(lootTex(true), 0.62, 0.53, 0.05));
  sack.userData.spr = ss;
  return {g, sack, chest, glow, coins, lbl, amt: -1};
}

// ---------------- 맵 만들기 ----------------
function build() {
  if (typeof R === 'undefined' || !R) return;
  if (world) { scene.remove(world.root); world.root.traverse(o => { if (o.geometry) o.geometry.dispose(); }); }
  evCache = new Map();
  const root = new THREE.Group();
  scene.add(root);
  const n = W * H, rows = R.map.rows;

  const floorM = worldUv(std(0xffffff, {roughness: 1, map: caveFloorTex()}));
  const ground = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 0.24, 1), floorM, n);
  ground.receiveShadow = true;
  const gBase = new Float32Array(n * 3), gn = vnoise(5, 64);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = y * W + x, r = 0.9 + 0.1 * gn(x / 5, y / 5);   // 밝기는 넓게 천천히만 바뀐다 (칸마다 다르면 판석처럼 보인다)
    COL.setRGB(r, r, r);
    gBase.set([COL.r, COL.g, COL.b], i * 3);
    M4.makeTranslation(wx(x), -0.12, wz(y));
    ground.setMatrixAt(i, M4);
    ground.setColorAt(i, COL);
  }
  root.add(ground);
  mesh(root, new THREE.PlaneGeometry(W + 40, H + 40).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: 0x000000}), 0, -0.3, 0, false);
  { // 칸 격자: 바닥 위의 가는 줄 (어느 확대에서도 1px 로 보인다). 바위는 줄을 가리고, 구덩이 둘레는 긋지 않는다
    const pit = new Set(R.map.traps.map(c => c[0] + ',' + c[1])), isPit = (x, y) => pit.has(x + ',' + y), gp = [];
    for (let y = 0; y <= H; y++) for (let x = 0; x < W; x++) if (!isPit(x, y) && !isPit(x, y - 1)) gp.push(x - W / 2, 0.011, y - H / 2, x + 1 - W / 2, 0.011, y - H / 2);
    for (let x = 0; x <= W; x++) for (let y = 0; y < H; y++) if (!isPit(x, y) && !isPit(x - 1, y)) gp.push(x - W / 2, 0.011, y - H / 2, x - W / 2, 0.011, y + 1 - H / 2);
    const gg = new THREE.BufferGeometry(); gg.setAttribute('position', new THREE.Float32BufferAttribute(gp, 3));
    const grid = new THREE.LineSegments(gg, new THREE.LineBasicMaterial({color: 0xcdbf9c, transparent: true, opacity: 0.15, depthWrite: false}));
    grid.renderOrder = 1; root.add(grid); }
  const curbM = std(0x6a5f52, {roughness: 1});
  const rock = buildRock(rows);
  root.add(rock.mesh);
  // 네 모서리 횃불 기둥: 둘레 바위 위에 선다
  const braziers = [];
  for (const [i, j] of [[-1, -1], [W, -1], [-1, H], [W, H]]) {
    const b = new THREE.Group();
    b.position.set(wx(i), rock.hAt(i, j) - 0.05, wz(j));
    mesh(b, new THREE.BoxGeometry(0.62, 0.3, 0.62), curbM, 0, 0.15, 0);
    mesh(b, new THREE.CylinderGeometry(0.17, 0.21, 1.5, 8), std(0x7d6648, {roughness: 0.85}), 0, 1.05, 0);
    mesh(b, new THREE.CylinderGeometry(0.3, 0.2, 0.18, 10), std(0x8a6a3a, {metalness: 0.6, roughness: 0.45}), 0, 1.88, 0);
    const fl = new THREE.Group();
    fl.position.y = 1.97;
    b.add(fl);
    mesh(fl, new THREE.ConeGeometry(0.2, 0.55, 10), new THREE.MeshBasicMaterial({color: 0xff7a1a}), 0, 0.22, 0, false);
    mesh(fl, new THREE.ConeGeometry(0.12, 0.36, 8), new THREE.MeshBasicMaterial({color: 0xffe08a}), 0, 0.16, 0, false);
    const L = new THREE.PointLight(0xff9a40, 9, 14, 1.4);
    L.position.y = 2.3;
    b.add(L);
    b.traverse(o => { if (o.isMesh) o.visible = false; });
    const bs = frameSprite('brazier', 0, 0.62, 2.3, 2 / 120) || pxSprite(brazierTex(0), 0.9, 2.25, 0.02);
    b.add(bs);
    root.add(b);
    braziers.push({fl, L, spr: bs});
  }

  const wallCells = [];
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (rows[y][x] === '#') wallCells.push([x, y]);
  const nW = Math.max(1, wallCells.length);
  // 이어진 벽 덩어리마다 같은 높이 (덩어리끼리는 다르게) — 붙은 벽이 한 바위처럼 보이게
  const isWall = (x, y) => x >= 0 && y >= 0 && x < W && y < H && rows[y][x] === '#';
  const comp = new Map(); let nc = 0;
  for (const [x0, y0] of wallCells) {
    if (comp.has(x0 + ',' + y0)) continue;
    const st = [[x0, y0]]; comp.set(x0 + ',' + y0, nc);
    while (st.length) { const [x, y] = st.pop(); for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { const k2 = (x + dx) + ',' + (y + dy); if (isWall(x + dx, y + dy) && !comp.has(k2)) { comp.set(k2, nc); st.push([x + dx, y + dy]); } } }
    nc++;
  }
  // 동굴 벽: 맵을 둘러싼 큰 바위와 종유석
  const rocks = [], spikes = [];
  const pad = 2.2, perim = (x0, z0, x1, z1, step) => { const pts = []; for (let x = x0; x <= x1; x += step) pts.push([x, z0], [x, z1]); for (let z = z0 + step; z < z1; z += step) pts.push([x0, z], [x1, z]); return pts; };
  perim(-W / 2 - pad, -H / 2 - pad, W / 2 + pad, H / 2 + pad, 1.5).forEach(([x, z], i) => rocks.push([x, z, i, 0]));
  perim(-W / 2 - pad - 2.5, -H / 2 - pad - 2.5, W / 2 + pad + 2.5, H / 2 + pad + 2.5, 2.2).forEach(([x, z], i) => rocks.push([x, z, i + 500, 1]));
  const rockM = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), std(0xffffff, {roughness: 1, map: rockPxTex()}), rocks.length);
  rocks.forEach(([x, z, i, ring], k) => {
    const h = hash(i, 3), sx = 1.1 + hash(i, 7) * 1.2, sy = (ring ? 2.6 : 1.2) + h * (ring ? 3.2 : 1.6);
    M4.compose(V3.set(x + (hash(i, 9) - 0.5) * 0.8, sy * 0.35 - 0.3, z + (hash(i, 11) - 0.5) * 0.8), Q.setFromEuler(new THREE.Euler(h, i, h * 2)), S3.set(sx, sy, sx * (0.8 + h * 0.4)));
    rockM.setMatrixAt(k, M4);
    const v = 0.16 + hash(i, 13) * 0.1; COL.setRGB(v, v * 0.85, v * 0.7); rockM.setColorAt(k, COL);
    if (hash(i, 17) < 0.35) spikes.push([x + (hash(i, 19) - 0.5) * 1.4, z + (hash(i, 23) - 0.5) * 1.4, i]);
  });
  rockM.castShadow = true; rockM.receiveShadow = true;
  const spikeM = new THREE.InstancedMesh(new THREE.BoxGeometry(0.5, 1, 0.5), std(0x8a7a66, {roughness: 1, map: rockPxTex()}), Math.max(1, spikes.length));
  spikes.forEach(([x, z, i], k) => { const h = 1.2 + hash(i, 29) * 2.4; M4.compose(V3.set(x, h / 2 - 0.1, z), Q.identity(), S3.set(0.6 + hash(i, 31) * 0.6, h, 0.6 + hash(i, 31) * 0.6)); spikeM.setMatrixAt(k, M4); });
  spikeM.count = spikes.length;
  root.add(rockM, spikeM);
  rockM.visible = spikeM.visible = false;                      // 둘레는 buildRock 의 동굴 벽이 맡는다     // LPC 화풍: 지도 바깥은 어둠 (Cambridge 처럼 판만 뜬다)
  // 바위 바닥 (맵 바깥)
  // 횃불 빛: 화면 가운데에 가까운 탐험가 6명의 횃불이 주변을 밝힌다 (빛 수를 고정해 셰이더를 다시 만들지 않는다)
  const torchL = [];
  for (let i = 0; i < 6; i++) { const L = new THREE.PointLight(0xff9a40, 0, 4.2, 1.5); root.add(L); torchL.push(L); }
  // 떠다니는 먼지
  const DN = 420, dpos = new Float32Array(DN * 3), dseed = new Float32Array(DN);
  for (let i = 0; i < DN; i++) { dpos.set([(hash(i, 41) - 0.5) * (W + 4), hash(i, 43) * 3.2, (hash(i, 47) - 0.5) * (H + 4)], i * 3); dseed[i] = hash(i, 53) * 100; }
  const dgeo = new THREE.BufferGeometry(); dgeo.setAttribute('position', new THREE.BufferAttribute(dpos, 3));
  const dust = new THREE.Points(dgeo, new THREE.PointsMaterial({size: 0.07, map: softTex(), color: 0xffd9a0, transparent: true, opacity: 0.45, depthWrite: false, blending: THREE.AdditiveBlending}));
  dust.userData = {base: dpos.slice(), seed: dseed};
  root.add(dust);

  // 바닥 장식: 빈 칸 몇 곳에 작은 돌 · 이끼 · 뼈 조각 (게임 물체와 헷갈리지 않게 작고 옅게)
  if (SHEETS.floor) {
    const occ = new Set([...R.map.ore, ...R.map.traps, ...R.map.bases, ...(R.map.wumpus || [])].map(c => c[0] + ',' + c[1]));
    const dg = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    const dm = [0, 1, 2].map(v => new THREE.MeshStandardMaterial({map: decoTex(v), transparent: true, alphaTest: 0.5, roughness: 1, opacity: 0.85}));
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (rows[y][x] === '#' || occ.has(x + ',' + y) || hash(x * 7 + 3, y * 11 + 5) > 0.16) continue;
      const v = hash(x, y * 3) < 0.45 ? 0 : hash(x, y * 3) < 0.85 ? 1 : 2;
      const m = new THREE.Mesh(dg, dm[v]); m.position.set(wx(x), 0.004, wz(y)); m.renderOrder = 1; root.add(m);
    }
  }
  // 금맥
  const oreMat = std(0xffc63a, {emissive: 0xd08a00, emissiveIntensity: 0.9, metalness: 0.8, roughness: 0.22, flatShading: true});
  const veinMat = new THREE.MeshBasicMaterial({color: 0xffd25a});
  const rockMat = std(0x3a2f26, {roughness: 0.9, flatShading: true});
  const rockG = new THREE.DodecahedronGeometry(0.34, 0), nug = new THREE.OctahedronGeometry(0.11, 0);
  const glowMat = new THREE.MeshBasicMaterial({map: softTex(), color: 0xffb030, transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending});
  const glowG = new THREE.PlaneGeometry(1.25, 1.25).rotateX(-Math.PI / 2);
  const ore = new Map();
  for (const [x, y] of R.map.ore) {
    const grp = new THREE.Group(), cs = [], h0 = hash(x, y);
    const glow = mesh(grp, glowG, glowMat.clone(), 0, 0.02, 0, false); glow.renderOrder = 1;
    const rock = mesh(grp, rockG, rockMat, 0, 0.1, 0);
    rock.scale.set(1.15, 0.6, 1.0); rock.rotation.set(h0, h0 * 6, 0);
    const r2 = mesh(grp, rockG, rockMat, 0.22, 0.05, -0.18); r2.scale.set(0.55, 0.4, 0.5); r2.rotation.y = h0 * 3;
    for (let k = 0; k < 3; k++) {                 // 바위 위를 가로지르는 금줄기
      const v = mesh(grp, new THREE.BoxGeometry(0.5, 0.025, 0.035), veinMat, (hash(x + k, y) - 0.5) * 0.2, 0.2 + k * 0.03, (k - 1) * 0.14, false);
      v.rotation.set(0, hash(x, y + k) * 3, (hash(y, x + k) - 0.5) * 0.6);
    }
    for (let k = 0; k < 7; k++) {                 // 튀어나온 금덩이 (남은 양만큼 보임)
      const t = k / 7 * Math.PI * 2 + h0 * 6, rr = 0.12 + hash(x + k, y + 3) * 0.2, sz = 0.7 + hash(x, y + k) * 0.7;
      const c = mesh(grp, nug, oreMat, Math.cos(t) * rr, 0.2 + hash(k, x) * 0.12, Math.sin(t) * rr);
      c.scale.set(sz, sz * 1.6, sz); c.rotation.set((hash(x + k, y) - 0.5) * 1.2, t, (hash(y, x + k) - 0.5) * 1.2);
      cs.push(c);
    }
    const glint = new THREE.Sprite(new THREE.SpriteMaterial({map: starTex(), color: 0xfff6d0, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending}));
    glint.position.set(0.1, 0.5, 0.05);
    grp.add(glint);
    grp.position.set(wx(x), 0, wz(y));
    const lbl = new THREE.Sprite(new THREE.SpriteMaterial({transparent: true, depthTest: false, sizeAttenuation: false}));
    lbl.position.set(0, 0.8, 0); lbl.scale.set(0.045, 0.0235, 1); lbl.renderOrder = 14; lbl.material.opacity = 0.8;
    grp.add(lbl);
    grp.traverse(o => { if (o.isMesh && o !== glow) o.visible = false; });
    cs.forEach(c => grp.remove(c));
    let osp;
    if (SHEETS.ore) {                              // LPC 금맥: 바위 위 금빛 수정
      const tx = SHEETS.ore.tex.clone(); tx.repeat.set(1 / 8, 1); tx.offset.set(7 / 8, 0); tx.needsUpdate = true;
      osp = new THREE.Sprite(new THREE.SpriteMaterial({map: tx, transparent: true, alphaTest: 0.5}));
      osp.center.set(0.5, 2 / 64); osp.scale.set(1.05, 1.05, 1); osp.renderOrder = 5; osp.userData.lpc = true; osp.material.color.setScalar(0.62);
    } else osp = pxSprite(oreTex(7), 0.95, 0.95, 0.08);
    grp.add(osp);
    const clk = pxSprite(clockTex(0, 12), 0.6, 0.115, 0.5);
    clk.position.set(-0.12, 0.07, 0.44);             // 칸 앞쪽 바닥에: 그 칸에 선 모험가의 머리 · 체력바와 겹치지 않는다 clk.renderOrder = 13; clk.material.depthTest = false;
    grp.add(clk);
    grp.userData.clk = clk;
    grp.userData.spr = osp;
    grp.userData.cs = cs; grp.userData.glint = glint; grp.userData.glow = glow; grp.userData.lbl = lbl;
    root.add(grp);
    ore.set(x + ',' + y, grp);
  }

  // 구덩이
  const traps = new Map();
  const ringGeo = new THREE.RingGeometry(0.25, 0.29, 28).rotateX(-Math.PI / 2);
  const shaftG = new THREE.CylinderGeometry(0.69, 0.6, 2.1, 4, 1, true).rotateY(Math.PI / 4);
  const shaftM = new THREE.MeshBasicMaterial({map: shaftTex(), side: THREE.BackSide});
  const rimM = std(0x4a3a28, {roughness: 0.95});
  for (const [x, y] of R.map.traps) {
    const hidden = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({color: 0xc0483a, transparent: true, opacity: 0.3, depthWrite: false}));
    hidden.position.set(wx(x), 0.012, wz(y));
    const rev = new THREE.Group();
    rev.position.set(wx(x), 0, wz(y));
    mesh(rev, shaftG, shaftM, 0, -1.05, 0, false);
    mesh(rev, new THREE.PlaneGeometry(0.96, 0.96).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: 0x000000}), 0, -2.08, 0, false);
    for (let i = 0; i < 4; i++) {                 // 갱도 입구의 무너진 돌
      const a = i * Math.PI / 2, h = hash(x + i, y + 7);
      const lip = mesh(rev, new THREE.BoxGeometry(0.96, 0.06, 0.08), rimM, Math.sin(a) * 0.46, -0.02 - h * 0.04, Math.cos(a) * 0.46);
      lip.rotation.y = a; lip.rotation.z = (h - 0.5) * 0.15;
      const ch = mesh(rev, new THREE.DodecahedronGeometry(0.05 + h * 0.04), rimM, Math.sin(a + 0.6) * 0.5, 0.01, Math.cos(a + 0.6) * 0.5);
      ch.scale.y = 0.55; ch.rotation.set(i, h * 6, 0);
    }
    rev.traverse(o => { if (o.isMesh) o.visible = false; });         // 낭떠러지: 칸 크기 그대로 뚫린 네모 구멍
    const shaft = new THREE.Mesh(new THREE.BoxGeometry(1, 2.1, 1), new THREE.MeshBasicMaterial({map: cliffTex(), side: THREE.BackSide}));
    shaft.geometry.groups = shaft.geometry.groups.filter(gr => gr.materialIndex !== 2 && gr.materialIndex !== 3);   // 뚜껑 · 바닥은 없앤다 (바닥은 끝없는 어둠)
    shaft.position.y = -1.05; rev.add(shaft);
    shaft.visible = false;
    { const pm = new THREE.Mesh(new THREE.PlaneGeometry(1.06, 1.06).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({map: pitHoleTex((x * 3 + y * 5) % 4), transparent: true, alphaTest: 0.5, roughness: 1}));
      pm.position.y = 0.005; pm.rotation.y = 0; pm.renderOrder = 1; pm.receiveShadow = true; rev.add(pm); }
    root.add(hidden, rev);
    traps.set(x + ',' + y, {hidden, rev, gi: y * W + x, gy: -0.12});
  }

  // 야영지
  const bases = R.map.bases.map(([x, y], t) => {
    const b = makeBase(t);
    b.g.position.set(wx(x), 0, wz(y));
    b.g.scale.setScalar(1.25);
    b.g.rotation.y = Math.atan2(W / 2 - 0.5 - x, H / 2 - 0.5 - y);
    root.add(b.g);
    return b;
  });

  // 웜퍼스
  const wum = (R.map.wumpus || []).map(([x, y], i) => {
    const w = makeWumpus();
    w.g.position.set(wx(x), 0, wz(y));
    w.g.scale.setScalar(1.7);
    w.g.rotation.y = i ? -0.35 : 0.35;              // 관전 카메라 (남쪽) 를 노려본다
    w.x = x; w.y = y; w.face = w.g.rotation.y;
    root.add(w.g);
    return w;
  });

  // 머릿속 표시
  const mind = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.86, 0.86).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({transparent: true, opacity: 0.5, depthWrite: false}), 3000);
  mind.count = 0; mind.renderOrder = 3;
  mind.setColorAt(0, COL.set(0xffffff));
  root.add(mind);
  const paths = new THREE.Group();
  root.add(paths);

  const s0 = Math.max(W, H);
  const sel = new THREE.Mesh(new THREE.RingGeometry(0.4, 0.48, 32).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: 0xffe2a0, transparent: true, depthWrite: false}));
  sel.position.y = 0.02;
  root.add(sel);

  const oreMax = new Map(R.map.ore.map(o => [o[0] + ',' + o[1], o[2]]));
  if (AGENT()) { hemi.intensity = 0.085; sun.intensity = 0.2; renderer.toneMappingExposure = 0.78; for (const b of braziers) b.L.distance = 5; rock.mesh.material.color.setScalar(1.7); }   // 동굴은 어둡다: 모험가가 선 칸만 밝다 (applyFog 의 LIT)
  else { hemi.intensity = 0.42; sun.intensity = 1.3; renderer.toneMappingExposure = 1.05; }
  world = {oreMax, revN: -1, root, ground, gBase, rock, pitsCut: true, wallCells, braziers, torchL, dust, ore, traps, bases, wum, loot: new Map(), mind, paths, sel, units: new Map(), fogKey: '', mindKey: ''};
  scene.fog.near = s0 * 1.4; scene.fog.far = s0 * 3.6;
  const s = Math.max(W, H);
  sun.position.set(-s * 0.35, s * 1.1, s * 0.55);
  sun.target.position.set(0, 0, 0);
  const sc = sun.shadow.camera;
  sc.left = -s * 0.8; sc.right = s * 0.8; sc.top = s * 0.8; sc.bottom = -s * 0.8; sc.near = 1; sc.far = s * 4;
  sc.updateProjectionMatrix();
  resetCam();
}

function resetCam() {
  const s = Math.max(W, H), d = s * 1.28;
  controls.target.set(0, 0, 0.6);
  camera.position.set(0, d * Math.cos(PHI), 0.6 + d * Math.sin(PHI));
  controls.update();
}

function resize() {
  const w = box.clientWidth, h = box.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h);
  composer.setPixelRatio(renderer.getPixelRatio());
  composer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

// ---------------- 상태 갱신 ----------------
function evOf(g) {
  let e = evCache.get(g);
  if (e) return e;
  e = {atk: new Map(), hit: new Map(), mine: new Set(), die: new Map(), push: new Map(), pushed: new Map(), whit: new Map(), eat: new Map(), scream: new Map(), stab: new Map(), list: F[g].e || []};
  for (const v of e.list) {
    if (v[0] === 'atk') { e.atk.set(v[1], v); if (v[6] > 0) e.hit.set(v[6], v); if (v[6] === -1) e.whit.set(v[4] + ',' + v[5], v); }
    else if (v[0] === 'push') { e.push.set(v[1], v); if (v[5] !== v[7] || v[6] !== v[8]) e.pushed.set(v[4], v); }
    else if (v[0] === 'eaten') e.eat.set(v[2] + ',' + v[3], v);
    else if (v[0] === 'stab') { e.stab.set(v[1], v); e.hit.set(v[6], v); }
    else if (v[0] === 'parrow') e.mine.add(v[1]);
    else if (v[0] === 'scream') e.scream.set(v[2] + ',' + v[3], v);
    else if (v[0] === 'mine' || v[0] === 'pick') e.mine.add(v[1]);
    else if (v[0] === 'die') e.die.set(v[1], v);
  }
  evCache.set(g, e);
  return e;
}

const LIT = 6;                                   // 모험가가 선 칸의 바닥 밝기 (어두운 바닥의 몇 배)
function applyFog(fi, team, vis, seen) {
  const key = fi + '|' + team;
  if (key === world.fogKey) return;
  world.fogKey = key;
  const fac = i => !vis ? 1 : vis[i] ? 1 : seen[i] ? 0.4 : 0.09;
  const lit = new Set();                         // 모험가 · 야영지가 선 칸만 밝다 ("자기 칸만 느낀다")
  if (AGENT()) {
    for (const u of F[fi].u) if (team < 0 || u[1] === team || (vis && vis[u[4] * W + u[3]])) lit.add(u[4] * W + u[3]);
    R.map.bases.forEach(([x, y], t) => { if (F[fi].bh[t] > 0) lit.add(y * W + x); });
  }
  for (let i = 0; i < W * H; i++) {
    const k = fac(i) * (lit.has(i) ? LIT : 1);
    COL.setRGB(world.gBase[i * 3] * k, world.gBase[i * 3 + 1] * k, world.gBase[i * 3 + 2] * k);
    world.ground.setColorAt(i, COL);
  }
  world.ground.instanceColor.needsUpdate = true;
  { const rk = world.rock, ca = rk.mesh.geometry.attributes.color, arr = ca.array, bs = rk.base, cl = rk.cells;   // 바위: 면마다 자기 칸의 밝기
    for (let f = 0; f < cl.length; f++) { const k = fac(cl[f]); for (let q = f * 9; q < f * 9 + 9; q++) arr[q] = bs[q] * k; }
    ca.needsUpdate = true; }
}

function updateStatic(fi, team, seen, now) {
  const om = oreAt[fi];
  for (const [k, grp] of world.ore) {
    const amt = om.get(k) || 0;
    const [x, y] = k.split(',').map(Number);
    grp.visible = !seen || seen[y * W + x] === 1;        // 다 캐도 빈 바위와 시계는 남는다
    if (!grp.visible) continue;
    const cs = grp.userData.cs, n = amt > 0 ? Math.max(1, Math.ceil(Math.min(1, amt / 16) * cs.length)) : 0;
    grp.userData.lbl.visible = amt > 0; grp.userData.glow.visible = amt > 0;
    { const RG = R.const.regrow || 12, full = amt >= (world.oreMax.get(k) || 0), clk = grp.userData.clk, st = fi % RG;
      clk.visible = !full;
      if (!full && clk.userData.st !== st) { clk.userData.st = st; clk.material.map = clockTex(st, RG); clk.material.needsUpdate = true; } }
    if (grp.userData.amt !== amt) { grp.userData.amt = amt; grp.userData.lbl.material.map = numTex(amt); grp.userData.lbl.material.needsUpdate = true; }
    cs.forEach((c, i) => c.visible = i < n);
    if (grp.userData.n !== n) { grp.userData.n = n;
      if (grp.userData.spr.userData.lpc) grp.userData.spr.material.map.offset.set(n / 8, 0);
      else { grp.userData.spr.material.map = oreTex(n); grp.userData.spr.material.needsUpdate = true; } }
    grp.scale.setScalar(0.85 + Math.min(1, amt / 16) * 0.25);
    grp.userData.glow.material.opacity = 0.35 + 0.2 * Math.sin(now * 1.6 + x + y);
    const tw = Math.max(0, Math.sin(now * 2.2 + x * 1.7 + y * 2.3));
    grp.userData.glint.material.opacity = tw * tw;
    grp.userData.glint.scale.setScalar(0.2 + tw * 0.4);
  }
  const rev = revAt[fi], changed = rev.size !== world.revN;
  world.revN = rev.size;
  for (const [k, t] of world.traps) {
    const [x, y] = k.split(',').map(Number);
    const r = true;                                // 구덩이는 처음부터 낭떠러지로 보인다 (봇은 바람으로만 안다)
    t.hidden.visible = false;
    t.rev.visible = !seen || seen[y * W + x] === 1;
    if (!world.pitsCut) { M4.makeTranslation(wx(x), t.gy, wz(y)); M4.scale(S3.set(0.001, 0.001, 0.001)); world.ground.setMatrixAt(t.gi, M4); }
    if (t.rev.visible) pitWind(wx(x), wz(y), now, x * 31 + y);
  }
  if (!world.pitsCut) { world.pitsCut = true; world.ground.instanceMatrix.needsUpdate = true; }
  // 떨어진 금: 자루 (10 이상은 보물 상자)
  const lm = lootAt[fi];
  for (const [k, o] of world.loot) if (!lm.has(k)) o.g.visible = false;
  for (const [k, amt] of lm) {
    const [x, y] = k.split(',').map(Number);
    let o = world.loot.get(k);
    if (!o) { o = makeLoot(); world.root.add(o.g); world.loot.set(k, o); }
    o.g.visible = !seen || seen[y * W + x] === 1;
    if (!o.g.visible) continue;
    const onDen = (R.map.wumpus || []).some(([a, b]) => a === x && b === y);
    o.g.position.set(wx(x) + (onDen ? 0.22 : 0), 0, wz(y) + (onDen ? 0.22 : 0));
    if (o.amt !== amt) { o.amt = amt; o.lbl.material.map = numTex(amt); o.lbl.material.needsUpdate = true; }
    o.chest.visible = amt >= 10; o.sack.visible = amt < 10;
    if (o.sack.userData.spr) o.sack.userData.spr.material.map.offset.set((amt >= 5 ? 1 : 0) / 3, 0);   // 적으면 주머니, 5 이상이면 주머니 더미
    o.g.scale.setScalar(amt >= 10 ? 1.25 : 0.85 + Math.min(1, amt / 6) * 0.35);
    o.sack.position.y = Math.abs(Math.sin(now * 2 + x + y)) * 0.03;
    o.glow.material.opacity = 0.4 + 0.2 * Math.sin(now * 2.4 + x * 3);
  }
  // 바닥에 꽂힌 화살 (궁수가 주울 수 있다)
  for (const [k, n] of arrAt[fi]) {
    const [x, y] = k.split(',').map(Number);
    if (seen && !seen[y * W + x]) continue;
    for (let i = 0; i < Math.min(n, 4); i++) {
      const m = fx('garrow2', () => pxSprite(garrowTex(), 0.34, 0.42, 0.05));
      const ox = (hash(x + i, y * 3) - 0.5) * 0.5, oz = (hash(x * 5, y + i) - 0.5) * 0.5;
      m.position.set(wx(x) + ox, 0, wz(y) + oz);
      m.scale.set(hash(i, x + y) < 0.5 ? -0.34 : 0.34, 0.42, 1);
    }
    if (n > 1) { const s2 = textSprite('×' + n, '#e8f2ff'); s2.position.set(wx(x) + 0.3, 0.55, wz(y) + 0.3); s2.scale.set(0.5, 0.25, 1); s2.material.opacity = 0.9; }
  }
  // 웜퍼스
  const wh = wumAt[fi];
  world.wum.forEach((w, i) => {
    const hp = wh[i], alive = hp > 0;
    w.g.visible = team < 0 || (!alive && seen && seen[w.y * W + w.x] === 1);
    if (!w.g.visible) return;
    w.dead.visible = !alive; w.live.visible = alive; w.hp.visible = alive; w.aura.visible = alive; if (w.bar) w.bar.visible = alive;
    if (R.const.wumpus_respawn) {                  // 쓰러진 굴: 다시 나타날 때까지 차오르는 시계
      if (!w.clk) { w.clk = new THREE.Sprite(new THREE.SpriteMaterial({transparent: true, depthTest: false})); w.clk.scale.set(0.5, 0.1, 1); w.clk.renderOrder = 14; w.g.add(w.clk); w.clk.position.set(0, 0.62, 0); }
      w.clk.visible = !alive;
      if (!alive) {
        let d0 = fi; while (d0 > 0 && wumAt[d0 - 1][i] <= 0) d0--;
        const RS = R.const.wumpus_respawn, st = Math.min(RS, fi - d0), k12 = Math.floor(st / RS * 12);
        if (w._ck !== k12) { w._ck = k12; w.clk.material.map = clockTex(k12, 12); w.clk.material.needsUpdate = true; }
      }
    }
    if (w.den) w.den.visible = alive; if (w.wsh) w.wsh.position.set(w.pix.position.x, 0.006, w.pix.position.z);
    if (!alive) return;
    w.aura.material.opacity = 0.12 + 0.06 * Math.sin(now * 2.2 + i);
    lpcFrame(w.pix, 'idle', 2, 0);
    const br = Math.sin(now * 1.7 + i * 2);
    w.body.scale.set(1 + br * 0.03, 1 - br * 0.025, 1 + br * 0.03);
    w.head.rotation.set(Math.sin(now * 0.9 + i) * 0.08, Math.sin(now * 0.6 + i) * 0.35, 0);
    w.jaw.rotation.x = 0.12 + Math.max(0, Math.sin(now * 0.7 + i)) * 0.25;
    w.arms.forEach((a, k) => { a.rotation.x = Math.sin(now * 1.3 + k * 2 + i) * 0.15; });
    const blink = (now * 0.5 + i * 0.37) % 1 < 0.03 ? 0.1 : 1;
    w.eyes.forEach(e => e.scale.y = 0.75 * blink);
    w.eyeL.intensity = 2.6 + Math.sin(now * 3 + i) * 0.6;
    setHp(w.hp, hp / (R.const.wumpus_hp || 9), 0x9adf3a);
    billboard(w.hp, w.g);
    w.hp.visible = false;                          // 머리 위 도트 체력바로
    if (!w.bar) { w.bar = new THREE.Sprite(new THREE.SpriteMaterial({transparent: true, depthTest: false})); w.bar.scale.set(0.42, 0.074, 1); w.bar.renderOrder = 14; w.g.add(w.bar); }
    { const k10 = Math.max(0, Math.min(10, Math.ceil(hp / (R.const.wumpus_hp || 9) * 10)));
      if (w._hk !== k10) { w._hk = k10; w.bar.material.map = hpTex(k10, -1); w.bar.material.needsUpdate = true; }
      w.bar.position.set(w.pix.position.x, 1.06, w.pix.position.z); w.bar.visible = true; }
    // 악취: 굴과 상하좌우 이웃에서 초록 안개가 피어오른다
    for (const [dx, dy] of [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const qx = w.x + dx, qy = w.y + dy;
      if (qx < 0 || qy < 0 || qx >= W || qy >= H || R.map.rows[qy][qx] === '#') continue;
      for (let k = 0; k < 3; k++) {
        const ph = (now * 0.32 + k / 3 + hash(qx * 3 + k, qy)) % 1, m = fx('stink', () => new THREE.Sprite(new THREE.SpriteMaterial({map: softTex(), color: 0x8fdc3a, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending})));
        m.position.set(wx(qx) + (hash(qx, qy + k) - 0.5) * 0.6, 0.1 + ph * 1.3, wz(qy) + (hash(qy, qx + k) - 0.5) * 0.6);
        m.scale.setScalar(0.5 + ph * 0.7);
        m.material.opacity = (dx || dy ? 0.18 : 0.26) * Math.sin(Math.PI * ph);
      }
    }
  });
}

function updateWumpus(g, a, moving, now) {
  if (!moving) { world.wum.forEach(w => { for (const m of w.flash) m.emissive.copy(m.userData.base); }); return; }
  const ev = evOf(g);
  world.wum.forEach((w, i) => {
    const k = w.x + ',' + w.y, hit = ev.whit.get(k), eat = ev.eat.get(k), scr = ev.scream.get(k);
    let fl = 0;
    if (hit && a > 0.45) fl = Math.max(0, 1 - (a - 0.45) / 0.45);
    for (const m of w.flash) m.emissive.copy(m.userData.base).lerp(HITC, fl);
    w.token.material.color.setRGB(1, 1 - fl * 0.65, 1 - fl * 0.65); w.pix.material.color.copy(w.token.material.color);
    if (hit && !scr && a > 0.45 && a < 0.9) { w.body.rotation.x = -0.25 * Math.sin(Math.PI * (a - 0.45) / 0.45); w.jaw.rotation.x = 0.6; }
    else w.body.rotation.x = 0;
    if (eat) {                                     // 덥석: 앞으로 달려들며 입을 크게 벌렸다 닫는다
      const [, , ex, ey] = eat, q = Math.sin(Math.PI * Math.min(1, a / 0.7));
      lpcFrame(w.pix, 'attack', 2, Math.floor(Math.min(0.999, a) * 6));
      w.body.position.z = q * 0.25; w.jaw.rotation.x = a < 0.45 ? 0.9 * (a / 0.45) : 0.9 * Math.max(0, 1 - (a - 0.45) / 0.2);
      w.arms.forEach(m => m.rotation.x = -1.4 * q);
    } else w.body.position.z = 0;
    if (scr) {                                     // 비명과 함께 쓰러진다
      w.g.visible = true; w.live.visible = a < 0.8; w.dead.visible = a >= 0.8; w.hp.visible = false;
      w.jaw.rotation.x = 1.0; w.head.rotation.x = -0.6 * Math.min(1, a * 2);
      w.body.rotation.z = a > 0.3 ? -easeOut(Math.min(1, (a - 0.3) / 0.5)) * 1.4 : Math.sin(now * 60) * 0.04;
      w.body.position.y = a > 0.3 ? -Math.min(1, (a - 0.3) / 0.5) * 0.15 : 0;
    } else { w.body.rotation.z = 0; w.body.position.y = 0; }
  });
}

function updateBases(fi, g, a, moving, seen, vis, now) {
  const ev = evOf(g);
  world.bases.forEach((b, t) => {
    const [x, y] = R.map.bases[t];
    b.g.visible = !seen || seen[y * W + x] === 1;
    const hp = F[fi].bh[t], dead = hp <= 0;
    b.core.visible = !dead; b.light.visible = !dead;
    const fl = 1 + Math.sin(now * 13 + t) * 0.12 + Math.sin(now * 23 + t * 3) * 0.08;
    b.core.scale.set(1, fl, 1); b.light.intensity = 3 * fl;
    b.flag.rotation.y = Math.sin(now * 3 + t) * 0.35;
    b.tent.scale.y = dead ? 0.3 : 1; b.tent.position.y = dead ? 0.2 : 0.47;
    b.pile.visible = !dead;
    let shake = 0;
    const hit = moving && ev.hit.get(R.map.base_ids[t]);
    { const dmg = moving && g > 0 ? F[g - 1].bh[t] - F[g].bh[t] : 0; if (dmg > 0 && b.g.visible) dmgText(dmg, wx(x), 2.3, wz(y), a, true); }
    if (hit && a > 0.45) shake = (1 - a) * 0.05;
    b.g.position.x = wx(x) + Math.sin(now * 70) * shake;
    for (const m of b.flash) m.emissive.setRGB(shake * 12, 0, 0);
    { const fr = Math.floor(now * 5 + t) % 2, key = (dead ? 1 : 0) + ':' + fr;
      if (b.spr.userData.camp) { const cm = b.spr.userData.camp, k5 = Math.floor(now * 9 + t * 2) % 5; b.spr.material.map.offset.set(((dead ? cm.dead[0] : cm.alive[0]) + k5) / cm.cols, 0); }
      else if (b._k !== key) { b._k = key; b.spr.material.map = campTex(t, dead, dead ? 0 : fr); b.spr.material.needsUpdate = true; }
      const kk = Math.min(1, shake * 14); b.spr.material.color.setRGB(1, 1 - kk * 0.6, 1 - kk * 0.6); }
    if (t === 0) for (const [k, br] of world.braziers.entries()) { const f2 = 1 + Math.sin(now * 11 + k * 2) * 0.1 + Math.sin(now * 19 + k) * 0.06; br.fl.scale.set(1, f2, 1); br.L.intensity = (AGENT() ? 2.2 : 9) * f2; if (br.spr.userData.cols) br.spr.material.map.offset.set((Math.floor(now * 8 + k) % 3) / 3, 0);
      else { const bf = Math.floor(now * 6 + k) % 2; if (br._f !== bf) { br._f = bf; br.spr.material.map = brazierTex(bf); br.spr.material.needsUpdate = true; } } }
    setHp(b.hp, hp / R.const.hp.B, TC[t].c);
    billboard(b.hp, b.g);
    { const hW = 1.98, th = b.g.rotation.y, wz2 = -hW * Math.cos(PHI), sc = b.g.scale.x;      // 천막 그림 꼭대기 바로 위 (화면 위쪽으로 올린다)
      b.hp.position.set(-Math.sin(th) * wz2 / sc, hW * Math.sin(PHI) / sc, Math.cos(th) * wz2 / sc); }
  });
}

function updateUnits(f, g, a, fi, team, vis, now) {
  const moving = g !== f, ev = evOf(g);
  for (const o of world.units.values()) { o.g.visible = false; if (o.tile) o.tile.visible = false; if (o.step) o.step.visible = false; if (o.gold) o.gold.visible = false; }
  const A = umap[f], B = umap[g];
  const show = (o, x, y, own) => {
    if (vis && !own && !vis[Math.round(y) * W + Math.round(x)]) return false;
    o.g.visible = true;
    o.x = x; o.y = y;
    o.g.position.set(wx(x), 0, wz(y));
    return true;
  };
  const getU = (u) => {
    let o = world.units.get(u[0]);
    if (!o) {
      o = makeChar(u[2], u[1]);
      world.root.add(o.g);
      o.tile = new THREE.Mesh(new THREE.PlaneGeometry(0.96, 0.96).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({map: footRingTex(), color: TC[u[1]].c, transparent: true, opacity: 0.3, depthWrite: false, blending: THREE.AdditiveBlending}));
      o.tile.renderOrder = 2; world.root.add(o.tile);
      o.step = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.3).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({map: perceptTex('steps'), transparent: true, opacity: 0.9, depthWrite: false}));
      o.step.renderOrder = 3; o.step.visible = false; world.root.add(o.step);     // 발소리: 머리 위 대신 발밑 칸 모서리에 (뭉쳐 있을 때 캐릭터를 가리지 않게)
      o.gold = new THREE.Sprite(new THREE.SpriteMaterial({map: goldTex(1), transparent: true, depthTest: false}));
      o.gold.renderOrder = 15; o.gold.visible = false; o.body.add(o.gold);
      world.units.set(u[0], o);
      o.g.rotation.y = Math.atan2(W / 2 - u[3], H / 2 - u[4]);
    }
    return o;
  };
  for (const u of F[g].u) {
    const id = u[0], p = A.get(id), o = getU(u);
    let x = u[3], y = u[4], st = 'idle';
    const atk = moving ? (ev.atk.get(id) || ev.stab.get(id)) : null, psh = moving ? ev.push.get(id) : null, pushed = moving ? ev.pushed.get(id) : null;
    if (pushed && p) {                                  // 밀려서 미끄러진다 (몸은 휘청)
      const e = easeOut(Math.min(1, Math.max(0, (a - 0.25) / 0.45)));
      x = p[3] + (u[3] - p[3]) * e; y = p[4] + (u[4] - p[4]) * e;
      st = 'stagger';
    } else if (psh) {
      st = 'push';
      o.face = Math.atan2(psh[5] - psh[2], psh[6] - psh[3]);
    } else if (moving && p && (p[3] !== u[3] || p[4] !== u[4])) {
      const e = ease(a);
      x = p[3] + (u[3] - p[3]) * e; y = p[4] + (u[4] - p[4]) * e;
      st = 'walk';
      o.face = Math.atan2(u[3] - p[3], u[4] - p[4]);
    } else if (atk) {
      st = atk[0] === 'stab' ? 'push' : 'attack';
      o.face = Math.atan2(atk[4] - atk[2], atk[5] - atk[3]);
    } else if (moving && ev.mine.has(id)) st = 'mine';
    if (!show(o, x, y, u[1] === team)) continue;
    if (o.face !== null) o.g.rotation.y = lerpAng(o.g.rotation.y, o.face, 0.3);
    { const th = o.g.rotation.y, off = 0.22 / CH; o.pix.position.set(-Math.sin(th) * off, 0, Math.cos(th) * off); o.token.position.set(-Math.sin(th) * off * 0.6, 0, Math.cos(th) * off * 0.6);
      o.shadow.position.set(o.pix.position.x, 0.006, o.pix.position.z); o.shadow.visible = NEAR > 0.3; }
    pose(o, st, a, now, id);
    if (o.pix.userData.lpc) { o.body.rotation.set(0, 0, 0); o.body.position.set(0, 0, 0); }   // 도트 그림은 몸을 기울이지 않는다 (체력바 · 아이콘이 딸려 움직인다)
    for (const fl of o.flames) fl.scale.set(1, 1 + Math.sin(now * 17 + id) * 0.18, 1);
    const sc = moving && !p ? elastic(Math.min(1, a * 1.3)) : 1;
    o.g.scale.setScalar(Math.max(0.001, sc) * CH * (o.kind === 'G' ? 1.12 : 1));
    o.disc.visible = false; o.badge.visible = false; o._fade = 1;
    o.tile.visible = true; o.tile.position.set(wx(Math.round(x)), 0.012, wz(Math.round(y)));
    o.step.visible = AGENT() && PERCEPT !== 'off' && !!u[12]; o.step.position.set(wx(Math.round(x)) + 0.31, 0.016, wz(Math.round(y)) + 0.31);
    o.tile.material.opacity = 0.3 + 0.06 * Math.sin(now * 2.4 + id);
    const fr = st === 'walk' ? 1 + (Math.floor(a * 4) % 2) : 0;
    if (!o.pix.userData.lpc && o._fr !== fr) { o._fr = fr; o.pix.material.map = bodyTex(o.kind, o.team, fr); o.pix.material.needsUpdate = true; o.glow.material.map = glowTex(o.kind, o.team, fr); o.glow.material.needsUpdate = true; }
    { const hov = (hoverC && hoverC[0] === Math.round(x) && hoverC[1] === Math.round(y)) || selId === id;
      o.glow.visible = hov && NEAR > 0.3; o.glow.material.opacity = 0.75 + 0.25 * Math.sin(now * 6);
      o.glow.scale.copy(o.pix.scale); o.glow.material.rotation = o.pix.material.rotation; o.glow.position.copy(o.pix.position);
      o.tile.material.color.setHex(hov ? TC[o.team].l : TC[o.team].c); }
    if (o.pix.userData.lpc) {                    // LPC 시트: 방향 줄과 동작 칸
      const dir = lpcDir(o.g.rotation.y), act = st === 'mine' || st === 'attack' || st === 'push';
      const an = st === 'walk' ? 'walk' : act ? 'attack' : 'idle', n = o.pix.userData.lpc.m[an].n;
      const col = st === 'walk' ? Math.floor(a * n) % n : act ? Math.floor(Math.min(0.999, a / 0.8) * n) : n > 1 ? Math.floor(now * 7 + id * 5) % n : 0;
      lpcFrame(o.pix, an, dir, col); lpcFrame(o.glow, an, dir, col);
      o.pix.position.y = o.glow.position.y = an === 'idle' && n === 1 && Math.sin(now * 2.4 + id * 1.7) > 0.6 ? 0.012 : 0;   // 숨쉬기: 가끔 한 도트 들썩
      o.pix.material.rotation = 0;
    } else {
    const sx = Math.sin(o.g.rotation.y);
    if (Math.abs(sx) > 0.3) o._left = sx < 0;
    o.pix.scale.x = o.pix.userData.w * (o._left ? -1 : 1);
    o.pix.material.rotation = st === 'mine' || st === 'attack' || st === 'push' ? Math.sin(Math.PI * Math.min(1, a / 0.6)) * 0.35 * (o._left ? 1 : -1) : 0;
    }
    lod(o);
    const src = moving && a < 0.5 && p ? p : u;
    o.pips.forEach((pp, i) => pp.visible = i < src[6]);
    const arr = o.kind === 'G' && src[8] !== undefined ? src[8] : -1;
    o.quiver.forEach((q, i) => q.visible = arr < 0 || i < arr);
    if (o.dagger) o.dagger.visible = arr === 0;
    const hp10 = Math.max(0, Math.min(10, Math.ceil(src[5] / R.const.hp[u[2]] * 10))), bk = src[6] + ':' + hp10 + ':' + arr;
    if (o._bk !== bk) { o._bk = bk; o.token.material.map = tokenTex(o.kind, o.team, src[6], hp10, arr); o.token.material.needsUpdate = true; }
    const mx = R.const.hp[u[2]];
    o.hp.visible = false;                          // 멀리서는 아이콘 고리, 가까이서는 머리 위 도트 막대
    // 도트 캐릭터는 카메라를 보고 서 있으므로, 머리 위 표시는 '화면 위쪽' 으로 올린다 (세계 높이로 올리면 화면 아래쪽 유닛은 몸통에 겹친다)
    const topW = (o.pix.userData.lpc ? o.pix.scale.y * 36 / 64 : 0.6) * CH, thG = o.g.rotation.y, gS = o.g.scale.x || CH;
    const above = (sp, hW) => { const wy = hW * Math.sin(PHI), wz2 = -hW * Math.cos(PHI); sp.position.set(o.pix.position.x - Math.sin(thG) * wz2 / gS, wy / gS, o.pix.position.z + Math.cos(thG) * wz2 / gS); };
    o.bar.visible = NEAR > 0.5; above(o.bar, topW + 0.1);
    { const cg = src[6], gd = o.gold;              // 든 금: 체력바 오른쪽 끝의 금화 (멀리서는 패의 오른쪽 위). 머리 높이라 앞뒤 유닛의 몸을 가리지 않는다
      gd.visible = cg > 0;
      if (cg > 0) {
        const cap = typeof R.const.carry === 'number' ? R.const.carry : 5, gk = cg + (cg >= cap ? 'f' : '');
        if (gd.userData.k !== gk) { gd.userData.k = gk; gd.material.map = goldTex(cg, cg >= cap); gd.material.needsUpdate = true; }
        const wpp = 2 * camera.position.distanceTo(o.g.position) * Math.tan(camera.fov * Math.PI / 360) / renderer.domElement.clientHeight;
        const sz = Math.min(40 * wpp, Math.max(17 * wpp, 0.3));     // 화면에서 17~40px
        const near = NEAR > 0.5, dx = near ? 0.27 + sz * 0.5 : 0.36;
        above(gd, near ? topW + 0.1 : 0.68 * CH - 0.14);
        gd.position.x += Math.cos(thG) * dx / gS; gd.position.z += Math.sin(thG) * dx / gS;
        const pop = moving && p && p[6] !== u[6] && a >= 0.5 ? 1 + 0.35 * Math.sin(Math.PI * Math.min(1, (a - 0.5) / 0.3)) : 1;   // 금이 바뀌는 순간 통 튄다
        gd.scale.set(sz * pop / gS, sz * pop / gS, 1);
      } }
    o.pool.visible = AGENT(); o.pool.scale.set(1 / CH, 1, 1 / CH);
    { const pv0 = A.get(id); if (moving && pv0 && u[5] < pv0[5]) dmgText(pv0[5] - u[5], o.g.position.x, 1.75, o.g.position.z, a); }
    { const pv = A.get(id), hurt = moving && pv && u[5] < pv[5];     // 지금 느끼는 것: 바람 · 악취 · 반짝임 · 부딪힘 · 발소리 · 아픔 → 머리 위 작은 아이콘 띠 (확대와 상관없이 같은 크기)
      const on = AGENT() && PERCEPT !== 'off' ? [u[7] && 'breeze', u[9] && 'stench', u[10] && 'glitter', u[11] && 'bump', hurt && 'hurt'].filter(Boolean) : [];
      const picked = (hoverC && hoverC[0] === Math.round(x) && hoverC[1] === Math.round(y)) || selId === id;
      const dot = PERCEPT === 'sel' && !picked;      // '선택만': 나머지는 작은 점 하나
      const ic = o.icons[0]; o.icons.forEach((x, k) => { if (k) x.visible = false; });
      ic.visible = on.length > 0;
      if (ic.visible) {
        const key = dot ? '.' : on.join(',');
        if (ic.userData.k !== key) { ic.userData.k = key; ic.material.map = dot ? perceptDot() : perceptStrip(on); ic.material.needsUpdate = true; ic.material.sizeAttenuation = false; }
        const sz = dot ? 0.008 : 0.02 * (picked ? 1 : ICONK);
        ic.scale.set(sz * (dot ? 1 : on.length), sz, 1);
        ic.center.set(0.5, 0); above(ic, NEAR > 0.5 ? topW + 0.2 : 0.68 * CH + 0.04);
      } }
    if (o._hk !== hp10) { o._hk = hp10; o.bar.material.map = hpTex(hp10, o.team); o.bar.material.needsUpdate = true; }
    setHp(o.hp, src[5] / mx, TC[u[1]].c);
    billboard(o.hp, o.g);
    const hit = moving && ev.hit.get(id);
    setFlash(o, hit && a > 0.45 ? Math.max(0, 1 - (a - 0.45) / 0.4) : 0);
    if (hit && a > 0.45 && a < 0.8) {            // 맞으면 뒤로 밀림
      const dx = u[3] - hit[2], dy = u[4] - hit[3], d = Math.hypot(dx, dy) || 1, k = Math.sin(Math.PI * (a - 0.45) / 0.35) * 0.12;
      o.g.position.x += dx / d * k; o.g.position.z += dy / d * k;
    }
    if (u[7] && (team < 0 || u[1] === team)) breeze(o.g.position, now, id, Math.round(x), Math.round(y));
    if (u[9] && (team < 0 || u[1] === team)) stink(o.g.position, now, id);
  }
  if (!moving) return;
  for (const u of F[f].u) {                       // 이번 라운드에 죽은 유닛
    if (B.has(u[0])) continue;
    const o = getU(u), d = ev.die.get(u[0]);
    let x = u[3], y = u[4];
    const trap = d && d[4] === 'trap', eaten = d && d[4] === 'wumpus';
    const pushedTo = ev.pushed.get(u[0]);
    if (d && (trap || eaten)) {
      const t0 = pushedTo ? 0.25 : 0, e = ease(Math.min(1, Math.max(0, (a - t0) * 2.5)));
      x = u[3] + (d[2] - u[3]) * e; y = u[4] + (d[3] - u[4]) * e;
    }
    if (!show(o, x, y, u[1] === team)) continue;
    o.hp.visible = false; o.disc.visible = o.badge.visible = false; o.bar.visible = false; o.glow.visible = false; o.icons.forEach(x => x.visible = false);
    o._fade = Math.max(0, 1 - Math.max(0, a - 0.55) / 0.45);
    lod(o);
    if (o.pix.userData.lpc) lpcFrame(o.pix, 'hurt', 0, Math.floor(Math.min(0.999, a * 1.25) * o.pix.userData.lpc.m.hurt.n));   // 쓰러지는 동작
    else o.pix.material.rotation = Math.min(1, a * 1.6) * Math.PI / 2 * (o._left ? -1 : 1);   // 옆으로 쓰러진다
    setFlash(o, 0);
    if (eaten) {                                   // 웜퍼스 입속으로 들려 올라가 사라진다
      const q = Math.max(0, (a - 0.35) / 0.65);
      pose(o, a < 0.35 ? 'walk' : 'stagger', a, now, u[0]);
      o.body.position.y = q * 0.8; o.body.rotation.z = q * 3;
      o.g.scale.setScalar(CH * Math.max(0.001, 1 - q));
      setFlash(o, q);
    } else if (trap) {                                    // 구덩이 속으로 빨려 떨어진다
      if (a < 0.4) { pose(o, 'walk', a * 2.5, now, u[0]); o.g.scale.setScalar(CH); }
      else {
        const q = (a - 0.4) / 0.6;
        pose(o, 'idle', 0, now, u[0]);
        o.shL.rotation.x = -2.8; o.shR.rotation.x = -2.8;
        o.body.position.y = 0.15 * Math.sin(Math.PI * Math.min(1, q * 4)) - q * q * 1.6;
        o.body.rotation.y = q * 5;
        o.g.scale.setScalar(CH * Math.max(0.001, 1 - q * 0.8));
      }
    } else {
      const q = Math.min(1, a * 1.6);
      pose(o, 'idle', 0, now, u[0]);
      o.body.rotation.x = -easeOut(q) * Math.PI / 2;
      o.body.position.y = -Math.max(0, a - 0.6) * 0.6;
      o.g.scale.setScalar(CH * (a > 0.75 ? Math.max(0.001, 1 - (a - 0.75) / 0.25) : 1));
    }
  }
}

function updateMind(fi, team) {
  const key = fi + '|' + team + '|' + mindMode + '|' + selId;
  if (key === world.mindKey) return;
  world.mindKey = key;
  const ids = mindIds(fi, team), d = F[fi].d || {};
  let c = 0;
  for (const id of ids) for (const [x, y, col] of (d[id].m || [])) {
    if (c >= 3000) break;
    M4.makeTranslation(wx(x), 0.015 + (c % 7) * 0.0005, wz(y));
    world.mind.setMatrixAt(c, M4);
    world.mind.setColorAt(c, COL.set(MINDHEX[col] !== undefined ? MINDHEX[col] : col));
    c++;
  }
  world.mind.count = c;
  world.mind.instanceMatrix.needsUpdate = true;
  if (world.mind.instanceColor) world.mind.instanceColor.needsUpdate = true;
  for (const ch of [...world.paths.children]) { world.paths.remove(ch); ch.geometry.dispose(); }
  for (const id of ids) for (const [col, pts] of (d[id].l || [])) {
    if (pts.length < 2) continue;
    const hex = MINDHEX[col] !== undefined ? MINDHEX[col] : col;
    const geo = new THREE.BufferGeometry().setFromPoints(pts.map(([x, y]) => new THREE.Vector3(wx(x), 0.12, wz(y))));
    const line = new THREE.Line(geo, new THREE.LineDashedMaterial({color: hex, dashSize: 0.22, gapSize: 0.14}));
    line.computeLineDistances();
    world.paths.add(line);
    const [ex, ey] = pts[pts.length - 1];
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.08, 10, 8), new THREE.MeshBasicMaterial({color: hex}));
    dot.position.set(wx(ex), 0.12, wz(ey));
    world.paths.add(dot);
  }
}

// ---------------- 효과 (재사용 풀) ----------------
const pool = {}, used = {};
function fx(type, make) {
  const arr = pool[type] || (pool[type] = []);
  const i = used[type] || 0;
  used[type] = i + 1;
  if (!arr[i]) { arr[i] = make(); scene.add(arr[i]); }
  arr[i].visible = true;
  return arr[i];
}
function fxBegin() { for (const k in used) used[k] = 0; for (const k in pool) for (const o of pool[k]) o.visible = false; }
const addMat = (c, o = 1) => new THREE.MeshBasicMaterial({color: c, transparent: true, opacity: o, depthWrite: false, blending: THREE.AdditiveBlending});
const ringG = new THREE.RingGeometry(0.85, 1, 40).rotateX(-Math.PI / 2);
const cubeG = new THREE.BoxGeometry(0.06, 0.06, 0.06);
const sphG = new THREE.SphereGeometry(1, 16, 12);
const windG = new THREE.TorusGeometry(0.42, 0.012, 4, 24, Math.PI * 0.55);
const AP0 = new THREE.Vector3(), AP1 = new THREE.Vector3();
function makeArrow() {
  const g = new THREE.Group();
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.72, 8), new THREE.MeshStandardMaterial({color: 0xead6a8, emissive: 0x7a5a30, emissiveIntensity: 0.7}));
  shaft.rotation.x = Math.PI / 2; g.add(shaft);
  const head = new THREE.Mesh(new THREE.ConeGeometry(0.06, 0.17, 8), new THREE.MeshBasicMaterial({color: 0xffffff}));
  head.rotation.x = Math.PI / 2; head.position.z = 0.43; g.add(head);
  const fl = [];
  for (const r of [0, Math.PI / 3, -Math.PI / 3]) {
    const f = new THREE.Mesh(new THREE.PlaneGeometry(0.18, 0.08), new THREE.MeshBasicMaterial({color: 0xffffff, side: THREE.DoubleSide}));
    f.rotation.set(0, Math.PI / 2, r); f.position.z = -0.3; g.add(f); fl.push(f);
  }
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({map: softTex(), color: 0xffffff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending}));
  glow.position.z = 0.42; glow.scale.setScalar(0.6); g.add(glow);
  const trail = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.055, 1.7, 8), addMat(0xffe2a0, 0.55));
  trail.rotation.x = Math.PI / 2; trail.position.z = -1.15; g.add(trail);
  g.userData = {head, trail, glow, fl};
  return g;
}
const laneG = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
function lane(x0, z0, x1, z1, color, op) {     // 화살이 지나는 줄: 바닥의 빛 궤적
  const m = fx('lane', () => new THREE.Mesh(laneG, addMat(0xffffff)));
  const len = Math.hypot(x1 - x0, z1 - z0) + 0.6;
  m.position.set((x0 + x1) / 2, 0.04, (z0 + z1) / 2);
  m.rotation.set(0, -Math.atan2(z1 - z0, x1 - x0), 0);
  m.scale.set(len, 1, 0.16);
  m.material.color.setHex(color); m.material.opacity = op; m.renderOrder = 2;
}
const pillarG = new THREE.CylinderGeometry(0.38, 0.38, 2.2, 24, 1, true);

function ring(x, z, y, r, color, op) {
  const m = fx('ring', () => new THREE.Mesh(ringG, addMat(0xffffff)));
  m.position.set(x, y, z); m.scale.setScalar(Math.max(0.01, r));
  m.material.color.setHex(color); m.material.opacity = op;
}
function burst(x, z, y0, n, color, a, speed, seed, grav = 4, size = 1) {
  for (let k = 0; k < n; k++) {
    const m = fx('p', () => new THREE.Mesh(cubeG, addMat(0xffffff)));
    const th = hash(seed, k) * Math.PI * 2, up = 0.4 + hash(k, seed) * 0.8, sp = speed * (0.5 + hash(seed + k, 7) * 0.7);
    const t = a * 0.9;
    m.position.set(x + Math.cos(th) * sp * t, Math.max(0.03, y0 + up * sp * t * 1.4 - grav * t * t * 0.5), z + Math.sin(th) * sp * t);
    m.material.color.setHex(color); m.material.opacity = Math.max(0, 1 - a);
    m.scale.setScalar(size * (1 - a * 0.5));
    if (SHEETS.floor) m.rotation.set(0, 0, 0); else m.rotation.set(t * 9 + k, t * 7, 0);   // 도트 화풍: 돌지 않는 네모 알갱이
  }
}
const texCache = new Map();
function textSprite(str, color) {
  const key = str + color;
  let tex = texCache.get(key);
  if (!tex && SHEETS.floor) { tex = pixelText(str, color, 12, 2).tex; texCache.set(key, tex); }
  if (!tex) {
    const c = document.createElement('canvas'); c.width = 128; c.height = 64;
    const g = c.getContext('2d');
    g.font = '800 44px Cinzel, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.lineWidth = 8; g.strokeStyle = '#000'; g.strokeText(str, 64, 34); g.fillStyle = color; g.fillText(str, 64, 34);
    tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
    texCache.set(key, tex);
  }
  const s = fx('txt', () => new THREE.Sprite(new THREE.SpriteMaterial({transparent: true, depthTest: false})));
  s.material.map = tex; s.material.needsUpdate = true; s.renderOrder = 20;
  return s;
}
const streakG = new THREE.PlaneGeometry(0.7, 0.03).rotateX(-Math.PI / 2);
function puff() { return new THREE.Sprite(new THREE.SpriteMaterial({map: softTex(), color: 0xdcecff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending})); }
function pitWind(px, pz, now, seed) {       // 구덩이 속에서 바람과 먼지가 소용돌이치며 솟는다
  for (let k = 0; k < 7; k++) {
    const ph = (now * 0.45 + k / 7 + hash(seed, k)) % 1, ang = now * 2.4 + k * 0.9 + seed;
    const m = fx('wisp', puff);
    const r = 0.18 + ph * 0.35;
    m.position.set(px + Math.cos(ang) * r, -0.6 + ph * 2.0, pz + Math.sin(ang) * r);
    m.scale.setScalar(0.18 + ph * 0.35);
    m.material.opacity = 0.32 * Math.sin(Math.PI * ph);
  }
  for (let i = 0; i < 2; i++) {
    const m = fx('wind', () => new THREE.Mesh(windG, addMat(0xd6f0ff)));
    const ph = (now * 0.6 + i * 0.5) % 1;
    m.position.set(px, 0.1 + ph * 1.1, pz);
    m.rotation.set(Math.PI / 2, 0, now * 3 + i * 3);
    m.scale.setScalar(0.7 + ph * 0.5);
    m.material.opacity = 0.45 * Math.sin(Math.PI * ph);
  }
}
function stink(pos, now, id) {             // 악취를 맡는 유닛: 머리 위로 초록 김이 꼬불꼬불 피어오른다
  for (let k = 0; k < 4; k++) {
    const ph = (now * 0.7 + k / 4 + id * 0.17) % 1, m = fx('stink', () => new THREE.Sprite(new THREE.SpriteMaterial({map: softTex(), color: 0x8fdc3a, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending})));
    m.position.set(pos.x + Math.sin(now * 3 + k * 1.7) * 0.18, 1.0 + ph * 0.9, pos.z + Math.cos(now * 2.5 + k) * 0.18);
    m.scale.setScalar(0.18 + ph * 0.3);
    m.material.opacity = 0.75 * Math.sin(Math.PI * ph);
  }
}
const _big = new Map();
function pixelText(str, color, px, fixedAsp) {   // 도트 글씨: 작은 캔버스에 그리고 반투명을 없앤 뒤, 위는 밝게 · 검은 테두리
  const f = `bold ${px}px "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif`;
  const m = document.createElement('canvas').getContext('2d'); m.font = f;
  const tw = Math.ceil(m.measureText(str).width) + 6, h = px + 6, w = fixedAsp ? Math.max(tw, Math.ceil(h * fixedAsp)) : tw;
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'); g.font = f; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = '#fff'; g.fillText(str, w / 2, h / 2 + 1);
  const d = g.getImageData(0, 0, w, h), a = d.data, on = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) on[i] = a[i * 4 + 3] > 110 ? 1 : 0;
  const col = rgbOf(color), hi = shade(color, 0.45), lo = shade(color, -0.25);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x, k = i * 4;
    if (on[i]) { const v = y < h * 0.42 ? hi : y > h * 0.7 ? lo : col; a[k] = v[0]; a[k + 1] = v[1]; a[k + 2] = v[2]; a[k + 3] = 255; continue; }
    let n = 0;
    for (let dy = -1; dy <= 1 && !n; dy++) for (let dx = -1; dx <= 1; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < w && yy < h && on[yy * w + xx]) { n = 1; break; } }
    if (n) { a[k] = 18; a[k + 1] = 10; a[k + 2] = 6; a[k + 3] = 255; } else a[k + 3] = 0;
  }
  g.putImageData(d, 0, 0);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.magFilter = t.minFilter = THREE.NearestFilter; t.generateMipmaps = false;
  return {tex: t, asp: w / h};
}
function bigText(str, color, h = 0.6) {     // 한글이 들어가는 큰 글자 (폭을 글자에 맞춘다)
  const key = str + color;
  let t = _big.get(key);
  if (!t && SHEETS.floor) { t = pixelText(str, color, 13); _big.set(key, t); }   // LPC 화풍: 도트 글씨
  if (!t) {
    const c = document.createElement('canvas'), g0 = c.getContext('2d');
    g0.font = '900 64px "Noto Serif KR", serif';
    const w = Math.ceil(g0.measureText(str).width) + 40;
    c.width = w; c.height = 96;
    const g = c.getContext('2d');
    g.font = '900 64px "Noto Serif KR", serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.lineWidth = 12; g.strokeStyle = '#000'; g.strokeText(str, w / 2, 50); g.fillStyle = color; g.fillText(str, w / 2, 50);
    t = {tex: new THREE.CanvasTexture(c), asp: w / 96}; t.tex.colorSpace = THREE.SRGBColorSpace;
    _big.set(key, t);
  }
  const s = fx('big', () => new THREE.Sprite(new THREE.SpriteMaterial({transparent: true, depthTest: false})));
  s.material.map = t.tex; s.material.needsUpdate = true; s.renderOrder = 21;
  s.scale.set(h * t.asp, h, 1);
  return s;
}
let PITSET = null;
function breeze(pos, now, id, cx, cy) {     // 바람을 느끼는 유닛: 구덩이 쪽에서 바람 줄기가 불어와 지나간다
  if (!PITSET || PITSET.r !== R) { PITSET = new Set(R.map.traps.map(([x, y]) => x + ',' + y)); PITSET.r = R; }
  const dirs = [];
  for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) if (PITSET.has((cx + dx) + ',' + (cy + dy))) dirs.push([-dx, -dy]);
  dirs.forEach(([dx, dy], j) => {
    const ang = Math.atan2(dx, dy);
    for (let k = 0; k < 4; k++) {
      const ph = (now * 1.1 + k / 4 + j * 0.37 + id * 0.13) % 1, side = (hash(id + k, j) - 0.5) * 0.7;
      const m = fx('streak', () => new THREE.Mesh(streakG, addMat(0xe6f4ff)));
      const d = -0.9 + ph * 1.8;
      m.position.set(pos.x + dx * d + dy * side, 0.25 + hash(k, id + j) * 0.7 + Math.sin(now * 4 + k) * 0.04, pos.z + dy * d - dx * side);
      m.rotation.set(0, ang + Math.PI / 2, 0);
      m.material.opacity = 0.7 * Math.sin(Math.PI * ph);
    }
  });
  for (let i = 0; i < 2; i++) {
    const m = fx('wind', () => new THREE.Mesh(windG, addMat(0xd6f0ff)));
    m.position.set(pos.x, 0.35 + i * 0.35 + Math.sin(now * 2 + i + id) * 0.05, pos.z);
    m.rotation.set(Math.PI / 2 + Math.sin(now + i) * 0.2, 0, now * (2.6 + i * 0.4) + i * 2.1 + id);
    m.scale.setScalar(0.85 + i * 0.15);
    m.material.opacity = 0.3 + 0.2 * Math.sin(now * 3 + i * 1.7);
  }
}

function dmgText(n, x, y, z, a, big) {             // 떠오르는 피해 숫자 (-3)
  if (a < 0.3) return;
  const q = (a - 0.3) / 0.7, sp = textSprite('-' + n, '#ff6a55'), k = big ? 1.3 : 1;
  sp.position.set(x, y + q * 0.6, z); sp.scale.set(0.7 * k, 0.35 * k, 1); sp.material.opacity = 1 - q * q; sp.renderOrder = 18;
}
// 6. 아슬아슬한 순간: 구덩이나 살아 있는 웜퍼스 굴 바로 옆 (상하좌우) 에 모험가가 서 있으면 그 칸이 심장처럼 두근거린다.
//    관전자는 위험을 보지만 모험가는 바람 · 악취만 느낀다는 것을 드러낸다
function dangerCells(fi, canSee) {
  const us = F[fi].u, out = [];
  const near = (x, y) => us.some(u => Math.abs(u[3] - x) + Math.abs(u[4] - y) === 1 && canSee(u[3], u[4]));
  if (showTraps) for (const [x, y] of R.map.traps) if (near(x, y)) out.push([x, y]);
  (R.map.wumpus || []).forEach(([x, y], i) => { if (((F[fi].w || [])[i] || 0) > 0 && near(x, y)) out.push([x, y]); });
  return out;
}
function dangerFx(fi, now, canSee) {
  const t = now * 5.4, beat = Math.pow(Math.max(0, Math.sin(t)), 8) + 0.6 * Math.pow(Math.max(0, Math.sin(t - 1.0)), 8);   // 두근, 두근
  for (const [x, y] of dangerCells(fi, canSee)) {
    ring(wx(x), wz(y), 0.06, 0.46 + beat * 0.14, 0xff3a2a, 0.3 + beat * 0.6);
    ring(wx(x), wz(y), 0.06, 0.3 + beat * 0.3, 0xff7a4a, beat * 0.35);
  }
}
function effects(g, a, canSee) {
  (R.map.wumpus || []).forEach(([x, y], i) => {     // 웜퍼스가 받은 피해
    const d = ((F[g - 1].w || [])[i] || 0) - ((F[g].w || [])[i] || 0);
    if (d > 0 && canSee(x, y)) dmgText(d, wx(x), 2.0, wz(y), a, true);
  });
  const baseIdx = id => R.map.base_ids.indexOf(id);
  for (const e of evOf(g).list) {
    const k = e[0];
    if (k === 'atk') {
      const [, id, ax, ay, tx, ty, tid] = e;
      if (!canSee(ax, ay) && !canSee(tx, ty)) continue;
      const u = umap[g].get(id) || umap[Math.max(0, g - 1)].get(id), bi = baseIdx(id), col = u ? TC[u[1]].l : bi >= 0 ? TC[bi].l : 0xffffff;
      if ((tid > 0 || tid === -1) && a > 0.45 && canSee(tx, ty)) {   // 피해 숫자: 맞은 자리 위로 떠오른다
        const q = (a - 0.45) / 0.55, s3 = textSprite('-' + (R.const.attack_damage || 3), '#ff5a48');
        s3.position.set(wx(tx), 1.25 + q * 0.6, wz(ty)); s3.scale.set(0.62, 0.31, 1); s3.material.opacity = 1 - q * q;
      }
      if (u && u[2] === 'E') {                    // 광부 근접 공격: 곡괭이를 휘둘러 번쩍
        if (a > 0.3 && a < 0.7) {                  // 도트 베기 호
          const q = (a - 0.3) / 0.4, sl = fx('slash', () => new THREE.Sprite(new THREE.SpriteMaterial({map: slashTex(), transparent: true, depthTest: false, blending: THREE.AdditiveBlending})));
          sl.position.set((wx(ax) + wx(tx)) / 2, 0.75, (wz(ay) + wz(ty)) / 2); sl.scale.setScalar(0.9 + q * 0.3);
          sl.material.rotation = Math.atan2(-(ty - ay), tx - ax) + (q - 0.5) * 1.6; sl.material.opacity = 1 - q; sl.material.color.setHex(TC[u[1]].l); sl.renderOrder = 19;
        }
        if (a > 0.3 && a < 0.85) {
          const q = (a - 0.3) / 0.55, tc2 = TC[u[1]].c;
          burst(wx(tx), wz(ty), 0.6, 12, 0xffffff, q, 1.8, id * 7 + g, 3, 0.9);
          ring(wx(tx), wz(ty), 0.6, 0.15 + q * 0.6, tc2, 1 - q);
          if (q < 0.4) { const st2 = fx('spark', () => new THREE.Sprite(new THREE.SpriteMaterial({map: starTex(), color: 0xffffff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending})));
            st2.position.set(wx(tx), 0.7, wz(ty)); st2.scale.setScalar(0.5 + q * 1.8); st2.material.opacity = 1 - q / 0.4; st2.material.color.setHex(tc2); }
        }
        continue;
      }
      const torch = !(R.const.rules && R.const.rules.unified) && baseIdx(tid) >= 0 && Math.abs(tx - ax) + Math.abs(ty - ay) === 1 && bi < 0;   // 횃불은 시안 1 규칙만
      if (torch) {                               // 횃불: 천막에 불이 붙어 솟는다
        if (a > 0.25) {
          const q = (a - 0.25) / 0.75;
          burst(wx(tx), wz(ty), 0.6, 18, 0xff8a2a, q, 1.2, id * 5 + g, -2.5, 1.6);
          burst(wx(tx), wz(ty), 0.5, 10, 0xffe08a, q, 0.8, id * 9 + g, -3, 1.1);
          ring(wx(tx), wz(ty), 0.1, 0.4 + q * 0.6, 0xff7a1a, 1 - q);
        }
        if (a < 0.6) { const s2 = bigText('횃불!', '#ffb347', 0.45); s2.position.set(wx(tx), 1.9 + a * 0.6, wz(ty)); s2.material.opacity = 1 - a / 0.6; }
        continue;
      }
      const dist = Math.abs(tx - ax) + Math.abs(ty - ay), fly = SHEETS.arrow ? Math.min(0.5, 0.26 + dist * 0.07) : Math.min(0.32, 0.12 + dist * 0.04);
      const tc = u ? TC[u[1]].c : bi >= 0 ? TC[bi].c : 0xffffff;
      if (a > 0.12) {                            // 조준선 → 빛 궤적 (쏘기 전에 가늘게, 날아가는 동안 밝게, 뒤에 사라짐)
        const op = a < 0.28 ? 0.12 * (a - 0.12) / 0.16 : a < 0.28 + fly ? 0.3 : 0.3 * Math.max(0, 1 - (a - 0.28 - fly) / 0.35);
        if (op > 0.01) lane(wx(ax), wz(ay), wx(tx), wz(ty), tc, op);
      }
      if (a > 0.28 && a < 0.28 + fly) {          // 화살이 줄을 따라 날아간다 (멀수록 오래)
        if (SHEETS.arrow) {                        // LPC 도트 화살: 포물선을 그리며 날아가는 투사체 (머리가 진행 방향, 꼬리에 잔상)
          const x0 = wx(ax), z0 = wz(ay), x1 = wx(tx), z1 = wz(ty), y0 = 0.72, H = 0.22 + dist * 0.12;
          const at = q => [x0 + (x1 - x0) * q, y0 + 4 * H * q * (1 - q) - 0.25 * q, z0 + (z1 - z0) * q];
          const q0 = (a - 0.28) / fly;
          for (let k = 3; k >= 0; k--) {           // k = 0 이 화살, 1..3 은 잔상
            const q = q0 - k * 0.07; if (q < 0) continue;
            const P = at(q), P2 = at(Math.min(1, q + 0.03));
            const sp = fx('larrow', () => { const t = SHEETS.arrow.tex.clone(); t.needsUpdate = true; return new THREE.Sprite(new THREE.SpriteMaterial({map: t, transparent: true, alphaTest: 0.05, depthTest: false})); });
            sp.position.set(P[0], P[1], P[2]);
            AP0.set(P[0], P[1], P[2]).project(camera); AP1.set(P2[0], P2[1], P2[2]).project(camera);
            sp.material.rotation = Math.atan2(AP1.y - AP0.y, (AP1.x - AP0.x) * camera.aspect);
            sp.scale.set(1.0, 1.0 * 7 / 33, 1); sp.renderOrder = 18 - k;
            sp.material.opacity = k ? 0.38 - k * 0.1 : 1; sp.material.color.setHex(k ? tc : 0xffffff);
          }
          continue;
        }
        const m = fx('arrow', makeArrow);
        const q = (a - 0.28) / fly, x0 = wx(ax), z0 = wz(ay), x1 = wx(tx), z1 = wz(ty), y0 = bi >= 0 ? 1.1 : 0.95;
        m.position.set(x0 + (x1 - x0) * q, y0 + (0.75 - y0) * q + Math.sin(Math.PI * q) * 0.1, z0 + (z1 - z0) * q);
        m.lookAt(x1, 0.75, z1);
        m.scale.setScalar(1.15);
        m.userData.trail.visible = true; m.userData.glow.visible = true;
        m.userData.head.material.color.setHex(col);
        m.userData.glow.material.color.setHex(tc); m.userData.glow.material.opacity = 0.9;
        m.userData.trail.material.color.setHex(col);
        for (const f of m.userData.fl) f.material.color.setHex(tc);
      }
      if (a >= 0.28 + fly) {
        const q = (a - 0.28 - fly) / (0.72 - fly);
        if (tid === -1) {                        // 웜퍼스에 명중: 초록 피와 고리
          burst(wx(tx), wz(ty), 0.8, 14, 0x9adf3a, q, 1.8, id * 31 + g, 3, 1.1);
          ring(wx(tx), wz(ty), 0.8, 0.3 + q * 0.7, 0xc8ff5a, 1 - q);
        } else if (tid === 0 || tid === -2) {    // 빗나감: 땅에 꽂힌 화살과 먼지
          const m = fx('arrow', makeArrow);
          const dx = Math.sign(tx - ax), dz = Math.sign(ty - ay);
          m.position.set(wx(tx) - dx * 0.15, 0.18, wz(ty) - dz * 0.15);
          m.lookAt(wx(tx) + dx, -0.8, wz(ty) + dz);
          m.userData.head.material.color.setHex(col); m.userData.trail.visible = false; m.userData.glow.visible = false; m.scale.setScalar(1.15);
          if (q < 0.5) burst(wx(tx), wz(ty), 0.1, 6, 0xa89880, q * 2, 0.8, id * 3 + g, 3, 0.8);
          continue;
        }
      }
      if (tid > 0 && a >= 0.28 + fly) {          // 명중: 번쩍임 · 고리 · 불똥
        const q = (a - 0.28 - fly) / (0.72 - fly);
        burst(wx(tx), wz(ty), 0.7, 12, 0xffffff, q, 2, id * 31 + g, 3, 1);
        ring(wx(tx), wz(ty), 0.7, 0.2 + q * 0.7, tc, 1 - q);
        if (q < 0.4) { const st2 = fx('spark', () => new THREE.Sprite(new THREE.SpriteMaterial({map: starTex(), color: 0xffffff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending})));
          st2.position.set(wx(tx), 0.8, wz(ty)); st2.scale.setScalar(0.6 + q * 2); st2.material.opacity = 1 - q / 0.4; st2.material.color.setHex(tc); }
      }
    } else if (k === 'trap') {
      const [, id, x, y] = e;
      if (!canSee(x, y)) continue;
      if (SHEETS.floor && a > 0.25) {               // 낭떠러지 추락: 도트 글씨와 함께 떨어지는 돌 부스러기
        const s2 = bigText('으악!', '#ffd2a0', 0.5); s2.position.set(wx(x), 1.7 + (a - 0.25) * 0.5, wz(y)); s2.material.opacity = Math.min(1, (1 - a) * 2.5);
        burst(wx(x), wz(y), 0.02, 10, 0x8a7a64, (a - 0.25) / 0.75, 0.6, id * 23 + g, 9, 1.1);
      }
      if (a < 0.35) continue;
      const q = (a - 0.35) / 0.65;                  // 무너지는 흙먼지
      ring(wx(x), wz(y), 0.04, 0.3 + q * 1.2, 0xb89a70, 0.7 * (1 - q));
      burst(wx(x), wz(y), 0.05, 16, 0xa88a60, q, 1.6, id * 17 + g, -1.2, 1.6);
    } else if (k === 'die') {
      const [id, x, y, cause] = [e[1], e[2], e[3], e[4]];
      if (!canSee(x, y)) continue;
      const bi = baseIdx(id);
      if (bi >= 0 && SHEETS.floor) {               // 야영지 파괴: 도트 불길 · 검은 연기 · 천막 조각 · 큰 도트 글씨
        burst(wx(x), wz(y), 0.4, 46, 0xff8a2a, a, 3.4, id + g, -0.5, 2.2);
        burst(wx(x), wz(y), 0.6, 30, 0xffe08a, a, 2.2, id * 3 + g, -1.2, 1.6);
        burst(wx(x), wz(y), 0.9, 26, 0x2a2420, a, 1.6, id * 5 + g, -2.2, 3.2);      // 검은 연기는 위로
        burst(wx(x), wz(y), 0.7, 18, TC[bi].c, a, 3, id * 7 + g, 5, 2);             // 팀 색 천막 조각
        ring(wx(x), wz(y), 0.05, 0.4 + a * 2.6, 0xff9a40, 1 - a);
        const s2 = bigText('야영지 파괴!', '#ff7a3d', 0.8); s2.position.set(wx(x), 2.3 + a * 0.6, wz(y)); s2.material.opacity = Math.min(1, (1 - a) * 2);
      } else if (bi >= 0) {
        const m = fx('flash', () => new THREE.Mesh(sphG, addMat(0xff8030)));
        m.position.set(wx(x), 0.6, wz(y)); m.scale.setScalar(0.3 + easeOut(a) * 2); m.material.opacity = 1 - a;
        m.material.color.setHex(TC[bi].c);
        burst(wx(x), wz(y), 0.5, 40, 0xffd080, a, 5, id + g, 6, 2);
      } else if (cause === 'atk' && a > 0.5) {
        burst(wx(x), wz(y), 0.3, 12, 0xd8dce6, (a - 0.5) * 2, 1.4, id * 13 + g, 3, 1);
      }
    } else if (k === 'mine') {                    // 금맥 공격: 멀면 금빛 줄이 날아가고, 금맥에서 금 부스러기가 튄다
      const [, id, ux, uy, tx0, ty0] = e, x = tx0 ?? ux, y = ty0 ?? uy;
      if (!canSee(x, y)) continue;
      if (Math.abs(x - ux) + Math.abs(y - uy) > 1 && a > 0.1 && a < 0.6) lane(wx(ux), wz(uy), wx(x), wz(y), 0xffd84a, 0.5 * (1 - (a - 0.1) / 0.5));
      if (a >= 0.4) burst(wx(x), wz(y), 0.2, 9, 0xffd84a, (a - 0.4) / 0.6, 1.6, id * 7 + g, 5, 0.8);
      if (a >= 0.4) { const q = (a - 0.4) / 0.6, s4 = textSprite('+1', '#ffd24a'); s4.position.set(wx(x) + 0.2, 1.0 + q * 0.5, wz(y)); s4.scale.set(0.46, 0.23, 1); s4.material.opacity = 1 - q * q; }
    } else if (k === 'dlv') {
      const [, id, amt, x, y] = e;
      if (!canSee(x, y)) continue;
      const s = textSprite('+' + amt, '#ffd978');
      s.position.set(wx(x), 1.1 + a * 0.9, wz(y)); s.scale.set(0.9, 0.45, 1); s.material.opacity = 1 - a * a;
      if (SHEETS.floor && e[5] != null) {         // 금화가 포물선을 그리며 야영지로 날아든다
        const [bx, by] = R.map.bases[e[5]];
        for (let i = 0; i < Math.min(amt, 6); i++) {
          const q = Math.min(1, Math.max(0, (a - i * 0.07) / 0.55)); if (q <= 0 || q >= 1) continue;
          const c = fx('coin', () => new THREE.Sprite(new THREE.SpriteMaterial({map: coinTex(), transparent: true, alphaTest: 0.4})));
          const jx = (hash(i, id) - 0.5) * 0.3;
          c.position.set(wx(x) + (wx(bx) - wx(x)) * q + jx * (1 - q), 0.7 + Math.sin(Math.PI * q) * 0.9, wz(y) + (wz(by) - wz(y)) * q);
          c.scale.setScalar(0.24); c.material.rotation = 0; c.renderOrder = 17;
        }
      }
    } else if (k === 'push') {
      const [, id, px, py, tid, fx0, fy0, tx, ty] = e;
      if (!canSee(fx0, fy0)) continue;
      const blocked = fx0 === tx && fy0 === ty, q = Math.max(0, (a - 0.2) / 0.8);
      if (a > 0.2) {
        ring(wx(fx0), wz(fy0), 0.5, 0.25 + q * 0.6, 0xfff1a0, 1 - q);
        const dx = fx0 - px, dz = fy0 - py;
        for (let k2 = 0; k2 < 3; k2++) {         // 밀린 쪽으로 뻗는 바람 줄기
          const m = fx('streak', () => new THREE.Mesh(streakG, addMat(0xe6f4ff)));
          const side = (k2 - 1) * 0.2, d = 0.2 + q * 0.8;
          m.position.set(wx(fx0) + dx * d + dz * side, 0.5 + k2 * 0.15, wz(fy0) + dz * d - dx * side);
          m.rotation.set(0, Math.atan2(dx, dz) + Math.PI / 2, 0);
          m.material.opacity = 0.8 * (1 - q);
        }
        if (!blocked) burst(wx(fx0), wz(fy0), 0.05, 8, 0xb89a70, q, 1.2, id * 7 + g, 2, 1.2);
      }
      if (a < 0.75) { const s2 = bigText(blocked ? '밀치기 (막힘)' : '밀치기!', '#fff1a0', 0.42); s2.position.set(wx(fx0), 1.45 + a * 0.4, wz(fy0)); s2.material.opacity = Math.min(1, (0.75 - a) * 3); }
    } else if (k === 'roar') {                      // 웜퍼스의 일격: 맨해튼 3 안의 한 명에게 강한 피해
      const [, x, y, ids] = e;
      if (!canSee(x, y)) continue;
      const rr = R.const.wumpus_roar || 2;
      ring(wx(x), wz(y), 0.06, 0.3 + a * (rr + 0.4), 0xb8ff4a, 0.8 * (1 - a));
      ring(wx(x), wz(y), 0.08, 0.2 + Math.max(0, a - 0.15) * (rr + 0.4), 0x5a8a2a, 0.6 * (1 - a));
      for (const tid of ids) {
        const u2 = umap[g].get(tid) || umap[Math.max(0, g - 1)].get(tid); if (!u2 || a < 0.35) continue;
        if (a < 0.8) lane(wx(x), wz(y), wx(u2[3]), wz(u2[4]), 0xb8ff4a, 0.7 * (1 - a));   // 굴에서 맞은 한 명에게 초록 공격 줄기
        burst(wx(u2[3]), wz(u2[4]), 0.5, 12, 0xb8ff4a, Math.max(0, (a - 0.35) / 0.65), 1.6, tid * 7 + g, 3, 1.2);
        const q = (a - 0.35) / 0.65, s3 = textSprite('-' + (R.const.wumpus_roar_dmg || 6), '#c8ff5a');
        s3.position.set(wx(u2[3]), 1.2 + q * 0.5, wz(u2[4])); s3.scale.set(0.56, 0.28, 1); s3.material.opacity = 1 - q * q;
      }
      const wi = (R.map.wumpus || []).findIndex(c => c[0] === x && c[1] === y);
      if (wi >= 0 && world.wum[wi] && world.wum[wi].pix) lpcFrame(world.wum[wi].pix, 'attack', 2, Math.floor(Math.min(0.999, a) * 7));
    } else if (k === 'wrespawn') {                  // 웜퍼스가 다시 나타난다
      const [, x, y] = e;
      const b = fx('beam', () => new THREE.Sprite(new THREE.SpriteMaterial({map: beamTex(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending})));
      b.center.set(0.5, 0); b.position.set(wx(x), 0, wz(y)); b.scale.set(1.2 * (1 - a * 0.4), 3.4, 1); b.material.color.setHex(0xb8ff4a); b.material.opacity = 1 - a; b.renderOrder = 17;
      burst(wx(x), wz(y), 0.2, 26, 0x8fdc3a, a, 2, x * 31 + y + g, -1.2, 1.6);
      const s2 = bigText('웜퍼스 부활!', '#c8ff5a', 0.7); s2.position.set(wx(x), 2.6 + a * 0.5, wz(y)); s2.material.opacity = Math.min(1, (1 - a) * 2);
    } else if (k === 'eaten') {
      const [, id, x, y] = e;
      if (!canSee(x, y)) continue;
      if (a > 0.4) { const q = (a - 0.4) / 0.6; burst(wx(x), wz(y), 1.0, 22, 0xd83a2a, q, 2, id * 11 + g, 4, 1.3); ring(wx(x), wz(y), 0.9, 0.3 + q, 0xff5a3a, 1 - q);
        if (SHEETS.floor) { burst(wx(x), wz(y), 0.2, 18, 0x4e7048, q, 2.6, id * 13 + g, 6, 1.6); ring(wx(x), wz(y), 0.03, 0.4 + q * 1.4, 0x8a7a64, 0.8 * (1 - q)); } }   // 골렘이 내려친 자리: 이끼 돌 조각 · 땅 울림
      const s2 = bigText('꿀꺽!', '#ff8a6a', 0.55); s2.position.set(wx(x), 2.2 + a * 0.6, wz(y)); s2.material.opacity = 1 - a * a;
    } else if (k === 'scream') {
      const [, id, x, y] = e;
      for (let i = 0; i < 3; i++) {              // 맵 전체로 퍼지는 비명의 고리
        const q = Math.max(0, a - i * 0.12);
        if (q > 0) ring(wx(x), wz(y), 0.3 + i * 0.25, 0.5 + q * Math.max(W, H) * 0.9, 0xc8ff5a, Math.max(0, 1 - q) * 0.9);
      }
      const m = fx('pillar', () => new THREE.Mesh(pillarG, addMat(0xffffff)));
      m.position.set(wx(x), 1.6, wz(y)); m.material.color.setHex(0xb8ff4a); m.material.opacity = 0.8 * (1 - a);
      m.scale.set(1.4 - a, 2.5, 1.4 - a);
      burst(wx(x), wz(y), 1.0, 30, 0xe4dcc2, a, 3, id + g, 5, 1.4);
      burst(wx(x), wz(y), 0.6, 22, 0x4e7048, a, 2.4, id * 7 + g, 6, 1.8);     // 이끼 낀 돌 조각
      const s2 = bigText('비명!', '#d8ff6a', 0.9); s2.position.set(wx(x), 2.8 + a * 0.8, wz(y)); s2.material.opacity = 1 - a * a;
    } else if (k === 'drop') {
      const [, x, y, amt] = e;
      if (!canSee(x, y)) continue;
      burst(wx(x), wz(y), 0.4, 6 + Math.min(14, amt), 0xffd25a, a, 1.8, x * 13 + y + g, 6, 1.3);
    } else if (k === 'pick') {
      const [, id, x, y, amt] = e;
      if (!canSee(x, y)) continue;
      burst(wx(x), wz(y), 0.2, 10, 0xffd84a, a, 1.2, id * 5 + g, -1.5, 1.1);
      const s2 = bigText('줍기 +' + amt, '#ffd978', 0.36); s2.position.set(wx(x), 1.6 + a * 0.8, wz(y)); s2.material.opacity = 1 - a * a;
    } else if (k === 'stab') {
      const [, id, ax, ay, tx, ty] = e;
      if (!canSee(tx, ty)) continue;
      if (a > 0.3) { const q = (a - 0.3) / 0.7; burst(wx(tx), wz(ty), 0.7, 8, 0xe6f0ff, q, 1.4, id * 7 + g, 3, 0.9); ring(wx(tx), wz(ty), 0.7, 0.15 + q * 0.4, 0xe6f0ff, 1 - q); }
      if (a < 0.7) { const s2 = bigText('단검!', '#e6f0ff', 0.36); s2.position.set(wx(tx), 1.5 + a * 0.4, wz(ty)); s2.material.opacity = Math.min(1, (0.7 - a) * 3); }
    } else if (k === 'parrow') {
      const [, id, x, y, n] = e;
      if (!canSee(x, y)) continue;
      burst(wx(x), wz(y), 0.2, 6, 0xdfeeff, a, 0.9, id * 3 + g, -2.5, 0.9);
      const s2 = bigText('화살 +' + n, '#dfeeff', 0.34); s2.position.set(wx(x), 1.6 + a * 0.7, wz(y)); s2.material.opacity = 1 - a * a;
    } else if (k === 'refill') {
      const [, id, x, y] = e;
      if (!canSee(x, y)) continue;
      ring(wx(x), wz(y), 0.05, 0.3 + a * 0.4, 0xcfe8ff, 1 - a);
      burst(wx(x), wz(y), 0.3, 8, 0xdfeeff, a, 0.7, id * 3 + g, -2, 0.8);
    } else if (k === 'spawn') {
      const [, id, t, kd, x, y] = e;
      if (!canSee(x, y)) continue;
      if (SHEETS.floor) {                          // 도트 빛기둥과 위로 튀는 팀 색 알갱이
        const b = fx('beam', () => new THREE.Sprite(new THREE.SpriteMaterial({map: beamTex(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending})));
        b.center.set(0.5, 0); b.position.set(wx(x), 0, wz(y)); b.scale.set(0.7 * (1 - a * 0.5), 2.6 * (0.6 + a * 0.4), 1);
        b.material.color.setHex(TC[t].l); b.material.opacity = 1 - a; b.renderOrder = 17;
        burst(wx(x), wz(y), 0.1, 14, TC[t].l, a, 1.4, id * 11 + g, -1.5, 1.2);
        ring(wx(x), wz(y), 0.03, 0.3 + a * 0.5, TC[t].c, 1 - a);
      } else {
      const m = fx('pillar', () => new THREE.Mesh(pillarG, addMat(0xffffff)));
      m.position.set(wx(x), 1.1, wz(y)); m.material.color.setHex(TC[t].c); m.material.opacity = 0.7 * (1 - a);
      m.scale.set(1 - a * 0.6, 1, 1 - a * 0.6);
      ring(wx(x), wz(y), 0.03, 0.3 + a * 0.4, TC[t].l, 1 - a);
      }
    }
  }
}

const TP = new THREE.Vector3();
function torches(now) {
  const list = [];
  for (const o of world.units.values()) if (o.g.visible && o.flames.length) { o.flames[0].getWorldPosition(TP); list.push([TP.distanceToSquared(controls.target), TP.clone(), o]); }
  list.sort((p, q) => p[0] - q[0]);
  world.torchL.forEach((L, i) => {
    if (i < list.length && !AGENT()) { L.position.copy(list[i][1]); L.intensity = 2.4 + Math.sin(now * 13 + i * 2) * 0.35 + Math.sin(now * 23 + i) * 0.2; }
    else L.intensity = 0;
  });
  const d = world.dust, pos = d.geometry.attributes.position, b = d.userData.base, sd = d.userData.seed;
  for (let i = 0; i < sd.length; i++) {
    const t = now * 0.12 + sd[i];
    pos.array[i * 3] = b[i * 3] + Math.sin(t * 1.3) * 0.6;
    pos.array[i * 3 + 1] = (b[i * 3 + 1] + now * 0.05 + Math.sin(t) * 0.2) % 3.2;
    pos.array[i * 3 + 2] = b[i * 3 + 2] + Math.cos(t * 1.1) * 0.6;
  }
  pos.needsUpdate = true;
}

// ---------------- 한 장면 그리기 ----------------
function frame(f, g, a, fi, team, vis, seen) {
  if (!world) build();
  if (!world) return;
  const now = performance.now() / 1000, moving = g !== f;
  const canSee = (x, y) => !vis || vis[y * W + x] === 1;
  fxBegin();
  { const d = camera.position.distanceTo(controls.target), s0 = Math.max(W, H);   // 처음 화면 (지도 전체) 부터 도트, 더 멀어지면 아이콘
    NEAR = Math.min(1, Math.max(0, (s0 * 1.44 - d) / (s0 * 0.12)));
    ICONK = Math.min(1, Math.max(0.55, s0 * 0.75 / d)); }
  if (world.wum) world.wum.forEach(w => { lod(w); const th = w.g.rotation.y, off = 0.3 / 1.7; w.pix.position.set(-Math.sin(th) * off, 0, Math.cos(th) * off); w.token.position.copy(w.pix.position).multiplyScalar(0.6); });
  applyFog(fi, team, vis, seen);
  updateStatic(fi, team, seen, now);
  updateBases(fi, g, a, moving, seen, vis, now);
  updateUnits(f, g, a, fi, team, vis, now);
  updateWumpus(g, a, moving, now);
  updateMind(fi, team);
  torches(now);
  if (moving) effects(g, a, canSee);
  if (AGENT()) dangerFx(fi, now, canSee);
  // 선택 고리
  let sx = null, sy = null;
  if (selId != null) {
    const bi = R.map.base_ids.indexOf(selId);
    if (bi >= 0) [sx, sy] = R.map.bases[bi];
    else { const o = world.units.get(selId); if (o && o.g.visible) { sx = o.x; sy = o.y; } }
  }
  if (fi === F.length - 1 && R.meta.winner >= 0) {          // 경기 끝: 이긴 야영지 위로 금빛 불꽃
    const [vx, vy] = R.map.bases[R.meta.winner];
    for (let k = 0; k < 3; k++) {
      const q = ((now + k * 0.45) % 1.35) / 1.35, seed = Math.floor((now + k * 0.45) / 1.35) * 7 + k;
      const ox = (hash(seed, 3) - 0.5) * 2.4, oz = (hash(seed, 5) - 0.5) * 2.4;
      burst(wx(vx) + ox, wz(vy) + oz, 2.2 + hash(seed, 9) * 1.2, 26, k === 1 ? TC[R.meta.winner].l : 0xffd25a, q, 2.6, seed, 1.5, 1.4);
      if (q < 0.25) ring(wx(vx) + ox, wz(vy) + oz, 2.4, 0.2 + q * 3, 0xffe8a0, 1 - q * 4);
    }
  }
  world.sel.visible = sx !== null;
  if (sx !== null) {
    world.sel.position.set(wx(sx), 0.02, wz(sy));
    world.sel.material.opacity = 0.6 + 0.4 * Math.sin(now * 5);
    world.sel.scale.setScalar(selId === R.map.base_ids[0] || selId === R.map.base_ids[1] ? 1.25 : 1);
  }
  // 관전 카메라: 싸움 · 사고가 난 곳을 부드럽게 따라간다
  if (spect) spectate(g);
  if (cine) cineStep();
  controls.update();
  // 화면 흔들림: 큰 사건 (구덩이 추락 · 처치 · 야영지 피격) 때 잠깐
  let amp = 0;
  if (moving && a > 0.35) {
    const k = Math.pow(1 - (a - 0.35) / 0.65, 2);
    for (const e of evOf(g).list) {
      if (e[0] === 'trap' && canSee(e[2], e[3])) amp = Math.max(amp, 0.16 * k);
      else if (e[0] === 'die' && e[4] === 'atk' && canSee(e[2], e[3])) amp = Math.max(amp, 0.08 * k);
      else if (e[0] === 'atk' && R.map.base_ids.includes(e[6]) && canSee(e[4], e[5])) amp = Math.max(amp, 0.05 * k);
      else if (e[0] === 'scream') amp = Math.max(amp, 0.3 * k);
      else if (e[0] === 'eaten' && canSee(e[2], e[3])) amp = Math.max(amp, 0.14 * k);
      else if (e[0] === 'push' && canSee(e[5], e[6])) amp = Math.max(amp, 0.04 * k);
    }
  }
  amp *= Math.min(1.5, camera.position.distanceTo(controls.target) / 12);
  if (amp > 0.001) {
    SH.set(Math.sin(now * 61) * amp, Math.sin(now * 47 + 1) * amp * 0.6, Math.cos(now * 53) * amp);
    camera.position.add(SH); composer.render(); camera.position.sub(SH);
  } else composer.render();
}

const SH = new THREE.Vector3(), FOC = new THREE.Vector3(), OFF = new THREE.Vector3();
let spect = false, focusPt = null, focusT = 0;
function setSpectate(on) { spect = on; focusPt = null; }
// 명장면 카메라: 큰 사건이 난 칸으로 다가갔다가, 끝나면 보던 자리로 돌아온다 (화면을 끌면 그만둔다)
let cine = null;
function cineStart(x, y) {
  if (!cine) cine = {home: [controls.target.clone(), camera.position.clone()]};
  cine.pt = [wx(x), wz(y)]; cine.out = false;
}
function cineEnd() { if (cine) cine.out = true; }
function cineStep() {
  if (!cine.out) {
    FOC.set(cine.pt[0], 0, cine.pt[1]);
    OFF.copy(camera.position).sub(controls.target);
    const len = OFF.length(), want = Math.min(len, 9);
    OFF.multiplyScalar((len + (want - len) * 0.08) / len);
    controls.target.lerp(FOC, 0.1);
    camera.position.copy(controls.target).add(OFF);
  } else if (spect) cine = null;                       // 관전 카메라가 켜져 있으면 돌아가지 않고 그쪽에 맡긴다
  else {
    controls.target.lerp(cine.home[0], 0.08); camera.position.lerp(cine.home[1], 0.08);
    if (camera.position.distanceTo(cine.home[1]) < 0.05) { controls.target.copy(cine.home[0]); camera.position.copy(cine.home[1]); cine = null; }
  }
}
function setPercepts(m) { PERCEPT = m === 'sel' || m === 'off' ? m : 'all'; }
function spectate(g) {
  const now = performance.now() / 1000;
  let sx = 0, sz = 0, n = 0;
  for (const e of evOf(g).list) {                       // 이번 라운드의 사건 자리
    if (e[0] === 'atk') { sx += wx(e[4]) + wx(e[2]); sz += wz(e[5]) + wz(e[3]); n += 2; }
    else if (e[0] === 'trap' || e[0] === 'die') { sx += wx(e[2]) * 3; sz += wz(e[3]) * 3; n += 3; }
    else if (e[0] === 'push') { sx += wx(e[5]) * 3; sz += wz(e[6]) * 3; n += 3; }
    else if (e[0] === 'eaten' || e[0] === 'scream') { sx += wx(e[2]) * 6; sz += wz(e[3]) * 6; n += 6; }
  }
  if (n) { focusPt = [sx / n, sz / n]; focusT = now; }
  else if (!focusPt || now - focusT > 2.5) {              // 사건이 없으면 적과 가까이 있는 유닛들 가운데
    const us = F[g].u; let bx = 0, bz = 0, m = 0;
    for (const u of us) for (const v of us) {
      if (u[1] !== v[1] && Math.max(Math.abs(u[3] - v[3]), Math.abs(u[4] - v[4])) <= 4) { bx += wx(u[3]); bz += wz(u[4]); m++; break; }
    }
    if (m) focusPt = [bx / m, bz / m];
    else { let cx = 0, cz = 0; for (const u of us) { cx += wx(u[3]); cz += wz(u[4]); } focusPt = us.length ? [cx / us.length, cz / us.length] : [0, 0]; }
    focusT = now;
  }
  FOC.set(focusPt[0], 0, focusPt[1]);
  OFF.copy(camera.position).sub(controls.target);
  const len = OFF.length();
  OFF.multiplyScalar((len + (13 - len) * 0.03) / len);
  controls.target.lerp(FOC, 0.04);
  camera.position.copy(controls.target).add(OFF);
}

// ---------------- 누르기 · 가리키기 ----------------
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), hitP = new THREE.Vector3();
function cellOf(ev) {
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set((ev.clientX - r.left) / r.width * 2 - 1, -(ev.clientY - r.top) / r.height * 2 + 1);
  ray.setFromCamera(ndc, camera);
  if (!ray.ray.intersectPlane(plane, hitP)) return null;
  return [Math.floor(hitP.x + W / 2), Math.floor(hitP.z + H / 2)];
}
let down = null;
renderer.domElement.addEventListener('pointerdown', ev => { down = [ev.clientX, ev.clientY]; });
controls.addEventListener('start', () => { cine = null; if (spect) { spect = false; if (window.onSpectateOff) window.onSpectateOff(); } });
renderer.domElement.addEventListener('pointerup', ev => {
  if (down && Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) < 5) { const c = cellOf(ev); if (c) selectCell(c[0], c[1]); }
  down = null;
});
renderer.domElement.addEventListener('pointermove', ev => { const c = cellOf(ev); hoverC = c; if (c) hoverCell(c[0], c[1]); });
renderer.domElement.addEventListener('pointerleave', () => { hoverC = null; });

function focus(x, y, d) {
  controls.target.set(wx(x), 0, wz(y));
  camera.position.set(wx(x), d * Math.cos(PHI), wz(y) + d * Math.sin(PHI));
  controls.update();
}

const LV = new THREE.Vector3();
function locate(x, y) {                        // 소리용: 그 칸이 화면 어디에 있나 → 좌우 (pan) 와 크기 (vol). 화면 밖 · 멀리 볼수록 작다
  if (!world) return {pan: 0, vol: 1};
  LV.set(wx(x), 0.5, wz(y)).project(camera);
  const off = Math.max(Math.abs(LV.x), Math.abs(LV.y)), s0 = Math.max(W, H), d = camera.position.distanceTo(controls.target);
  const zoom = Math.min(1.2, Math.max(0.55, Math.sqrt(s0 * 1.28 / Math.max(1, d)) * 0.8));     // 전체 화면 0.8, 확대하면 커진다
  const edge = off <= 1 ? 1 : Math.max(0.15, 1 - (off - 1) * 0.9);                             // 화면 밖은 멀어질수록 작게
  return {pan: Math.max(-0.85, Math.min(0.85, LV.x * 0.85)), vol: zoom * edge};
}

function look(x, y, z, tx, ty, tz) {          // 확인용: 카메라를 칸 좌표로 직접 놓는다
  camera.position.set(wx(x), y, wz(z)); controls.target.set(wx(tx), ty, wz(tz)); controls.update();
}

function legend() {                          // 오른쪽 '표시' 칸에 쓸 그림: 화면에 실제로 그리는 것과 같은 도트 아이콘
  const u = t => t.image.toDataURL(), o = {};
  for (const k of ['breeze', 'stench', 'glitter', 'bump', 'steps', 'hurt']) o[k] = u(perceptTex(k));
  o.hp = u(hpTex(10, 0)); o.hpLow = u(hpTex(3, 0)); o.token = u(tokenTex('E', 0)); o.pit = u(pitHoleTex(0)); o.gold = u(goldTex(3));
  return o;
}

window.View3D = {build, frame, resize, resetCam, focus, setSpectate, setPercepts, cineStart, cineEnd, dangerCells, look, legend, locate, dbg: () => world};
if (window.onView3DReady) window.onView3DReady();
