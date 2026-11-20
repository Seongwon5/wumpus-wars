// 3D 뷰 (three.js, MIT 라이선스). viewer.html 안에 <script type="module"> 로 끼워 넣는다.
// 리플레이 상태 (R, F, P, umap, ...) 는 viewer.html 본체의 전역 변수를 읽기만 한다.
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';

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
controls.enableDamping = true;
controls.maxPolarAngle = 1.32;
controls.minDistance = 4;
controls.maxDistance = 90;

scene.add(new THREE.HemisphereLight(0xffe0b0, 0x1a1008, 0.5));
const sun = new THREE.DirectionalLight(0xffd59a, 1.7);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.02;
scene.add(sun, sun.target);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.75, 0.5, 0.78);
composer.addPass(bloom);
composer.addPass(new OutputPass());

const TC = [{c: 0xff4a3a, d: 0x9a2216, l: 0xffc2b0, css: '#ff4a3a'}, {c: 0x2ec4ff, d: 0x125f86, l: 0xbfeaf5, css: '#2ec4ff'}];
const MINDHEX = {green: 0x50dc78, red: 0xff4646, yellow: 0xffc83c, blue: 0x50a0ff, purple: 0xb46eff, white: 0xffffff};
const CH = 1.25;                       // 캐릭터 크기
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

let _star = null, _hole = null, _shaft = null, _soft = null;
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
  g.beginPath(); g.roundRect(4, 4, 120, 56, 18); g.fillStyle = 'rgba(14,9,5,0.88)'; g.fill();
  g.lineWidth = 4; g.strokeStyle = '#d9a441'; g.stroke();
  g.fillStyle = '#ffd978'; g.font = '800 50px Cinzel, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(String(n), 64, 36);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  _num.set(n, t);
  return t;
}
function badgeTex(kind, team, carry = 0) {
  const key = kind + team + ':' + carry;
  if (_badge.has(key)) return _badge.get(key);
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), col = TC[team].css;
  const shape = (r) => {
    g.beginPath();
    if (kind === 'G') { for (let i = 0; i < 6; i++) { const t = i / 6 * Math.PI * 2 + Math.PI / 6; g.lineTo(128 + Math.cos(t) * r, 128 + Math.sin(t) * r); } g.closePath(); }
    else g.arc(128, 128, r, 0, 7);
  };
  shape(122); g.fillStyle = '#0b0705'; g.fill();               // 바깥 검은 테
  shape(112); g.fillStyle = col; g.fill();                     // 팀 색 테두리
  shape(90); g.fillStyle = '#1a110a'; g.fill();                // 어두운 바탕
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
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  _badge.set(key, t);
  return t;
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
  const T = TC[team], G = kind === 'G';
  const g = new THREE.Group(), body = new THREE.Group();
  g.add(body);
  const mTeam = std(T.c, {roughness: 0.45, emissive: T.c, emissiveIntensity: 0.28}), mDark = std(T.d, {roughness: 0.6, emissive: T.c, emissiveIntensity: 0.12}), mSkin = std(0xf0c9a0);
  const mMetal = std(0xa7b0bf, {metalness: 0.7, roughness: 0.3}), mWood = std(0x7a4f28), mBlack = std(0x1a1d24), mLeather = std(0x5a3a1e, {roughness: 0.8});
  const RB = (w, h, d, r = 0.03) => new RoundedBoxGeometry(w, h, d, 2, r);

  const leg = (sx) => {
    const hip = new THREE.Group();
    hip.position.set(sx, 0.3, 0);
    body.add(hip);
    mesh(hip, RB(0.1, 0.28, 0.11), mDark, 0, -0.14, 0);
    mesh(hip, RB(0.11, 0.05, 0.16, 0.02), mBlack, 0, -0.28, 0.025);
    return hip;
  };
  const hipL = leg(-0.075), hipR = leg(0.075);
  mesh(body, RB(G ? 0.3 : 0.28, 0.3, G ? 0.2 : 0.18, 0.05), G ? mLeather : mTeam, 0, 0.45, 0);
  if (G) mesh(body, RB(0.26, 0.2, 0.235, 0.03), mTeam, 0, 0.46, 0);          // 갑옷 위 팀 색 조끼
  mesh(body, RB(G ? 0.35 : 0.29, 0.04, G ? 0.23 : 0.19, 0.01), mBlack, 0, 0.31, 0);
  mesh(body, new THREE.SphereGeometry(0.11, 18, 14), mSkin, 0, 0.7, 0);
  mesh(body, new THREE.BoxGeometry(0.025, 0.035, 0.01), mBlack, -0.04, 0.72, 0.105, false);
  mesh(body, new THREE.BoxGeometry(0.025, 0.035, 0.01), mBlack, 0.04, 0.72, 0.105, false);

  const pips = [], flames = [];
  if (!G) {
    // 중절모
    mesh(body, new THREE.CylinderGeometry(0.2, 0.2, 0.018, 22), mLeather, 0, 0.78, 0);
    mesh(body, new THREE.CylinderGeometry(0.095, 0.118, 0.12, 18), mLeather, 0, 0.845, 0);
    mesh(body, new THREE.CylinderGeometry(0.12, 0.12, 0.03, 18), mDark, 0, 0.8, 0);
    mesh(body, RB(0.22, 0.24, 0.1), mWood, 0, 0.47, -0.14);                    // 배낭
    const pm = std(0xffc63a, {emissive: 0xc98a00, emissiveIntensity: 1.1, metalness: 0.6, roughness: 0.3, flatShading: true});
    for (let i = 0; i < 5; i++) {
      const p = mesh(body, new THREE.DodecahedronGeometry(0.038), pm, -0.08 + i * 0.04, 0.61, -0.14, false);
      pips.push(p);
    }
  } else {
    // 두건과 망토
    mesh(body, new THREE.SphereGeometry(0.135, 18, 12, 0, Math.PI * 2, 0, Math.PI * 0.62), mDark, 0, 0.71, -0.008);
    const tip = mesh(body, new THREE.ConeGeometry(0.07, 0.16, 10), mDark, 0, 0.78, -0.12);
    tip.rotation.x = -1.1;
    const cape = mesh(body, new THREE.BoxGeometry(0.32, 0.42, 0.02), mDark, 0, 0.4, -0.13);
    cape.rotation.x = 0.12;
    // 화살통
    const q = mesh(body, new THREE.CylinderGeometry(0.05, 0.045, 0.3, 10), mLeather, 0.08, 0.52, -0.16);
    q.rotation.z = -0.35;
    for (let i = 0; i < 3; i++) {
      const f = mesh(body, new THREE.ConeGeometry(0.018, 0.07, 4), std(0xf2ead8), 0.13 + i * 0.022, 0.7 + i * 0.01, -0.16 + (i - 1) * 0.02, false);
      f.rotation.z = -0.35;
    }
  }

  const arm = (sx) => {
    const sh = new THREE.Group();
    sh.position.set(sx, 0.57, 0);
    body.add(sh);
    mesh(sh, RB(0.08, 0.26, 0.08), G ? mDark : mTeam, 0, -0.13, 0);
    mesh(sh, new THREE.SphereGeometry(0.045, 10, 8), mSkin, 0, -0.28, 0);
    const hand = new THREE.Group();
    hand.position.set(0, -0.28, 0);
    sh.add(hand);
    return {sh, hand};
  };
  const L = arm(G ? -0.2 : -0.18), Rr = arm(G ? 0.2 : 0.18);
  if (!G) {           // 곡괭이와 횃불
    const handle = mesh(Rr.hand, new THREE.CylinderGeometry(0.017, 0.017, 0.44, 8), mWood, 0, 0, 0.17);
    handle.rotation.x = Math.PI / 2;
    const head = mesh(Rr.hand, new THREE.BoxGeometry(0.3, 0.04, 0.04), mMetal, 0, 0, 0.37);
    head.rotation.z = 0.1;
    const stick = mesh(L.hand, new THREE.CylinderGeometry(0.018, 0.014, 0.3, 8), mWood, 0, 0.1, 0.05);
    stick.rotation.x = 0.35;
    const fl = new THREE.Group();
    fl.position.set(0, 0.26, 0.1);
    L.hand.add(fl);
    mesh(fl, new THREE.ConeGeometry(0.045, 0.14, 10), new THREE.MeshBasicMaterial({color: 0xffa040}), 0, 0.05, 0, false);
    mesh(fl, new THREE.ConeGeometry(0.025, 0.09, 8), new THREE.MeshBasicMaterial({color: 0xfff0a0}), 0, 0.03, 0, false);
    flames.push(fl);
  } else {            // 활
    const bow = new THREE.Group();
    bow.position.set(0, 0, 0.05);
    L.hand.add(bow);
    const limb = mesh(bow, new THREE.TorusGeometry(0.28, 0.016, 6, 24, Math.PI * 0.9), mWood, 0, 0, 0);
    limb.rotation.set(0, Math.PI / 2, Math.PI / 2 - Math.PI * 0.45);
    const str = mesh(bow, new THREE.CylinderGeometry(0.004, 0.004, 0.5, 4), std(0xf2ead8), 0, 0, -0.04, false);
    str.position.z = -0.07;
    mesh(L.hand, new THREE.CylinderGeometry(0.022, 0.022, 0.07, 8), mLeather, 0, 0, 0.05);
  }
  const hp = hpBar(0.6);
  hp.position.y = 1.0;
  g.add(hp);
  const seg = G ? 6 : 32;
  const disc = new THREE.Group();
  const fillD = new THREE.Mesh(new THREE.CircleGeometry(0.36, seg).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: T.c, transparent: true, opacity: 0.28, depthWrite: false}));
  const rimD = new THREE.Mesh(new THREE.RingGeometry(0.33, 0.4, seg).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: T.c, transparent: true, opacity: 0.95, depthWrite: false}));
  if (G) { fillD.rotation.y = rimD.rotation.y = Math.PI / 6; }
  disc.add(fillD, rimD); disc.position.y = 0.015; disc.renderOrder = 4;
  g.add(disc);
  const badge = new THREE.Sprite(new THREE.SpriteMaterial({map: badgeTex(kind, team), color: 0xb4b4b4, transparent: true, depthTest: false, sizeAttenuation: false}));
  badge.position.y = 1.22; badge.scale.set(0.027, 0.027, 1); badge.renderOrder = 15;      // 화면에서 늘 같은 크기
  g.add(badge);
  g.traverse(o => { if (o.isMesh && o.castShadow) o.receiveShadow = true; });
  for (const m of [mTeam, mDark, mSkin]) m.userData.base = m.emissive.clone();
  return {g, body, hipL, hipR, shL: L.sh, shR: Rr.sh, pips, flames, hp, disc, badge, flash: [mTeam, mDark, mSkin], kind, team, face: null, x: 0, y: 0};
}

function setFlash(o, k) {
  if (o._flash === k) return;
  o._flash = k;
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
  } else {                                                        // 숨쉬기
    const b = Math.sin(now * 2.2 + id);
    body.position.y = b * 0.012;
    shL.rotation.z += 0.05 + b * 0.03; shR.rotation.z = -0.05 - b * 0.03;
  }
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
  const hp = hpBar(1.0);
  hp.position.y = 1.55;
  g.add(hp);
  g.traverse(o => { if (o.isMesh) o.receiveShadow = true; });
  return {g, core, flag, fire, light, tent, pile, hp, flash: [stone, cloth], team: t};
}

// ---------------- 맵 만들기 ----------------
function build() {
  if (typeof R === 'undefined' || !R) return;
  if (world) { scene.remove(world.root); world.root.traverse(o => { if (o.geometry) o.geometry.dispose(); }); }
  evCache = new Map();
  const root = new THREE.Group();
  scene.add(root);
  const n = W * H, rows = R.map.rows;

  const ground = new THREE.InstancedMesh(new RoundedBoxGeometry(0.97, 0.24, 0.97, 2, 0.05), std(0xffffff, {roughness: 0.95}), n);
  ground.receiveShadow = true;
  const gBase = new Float32Array(n * 3);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = y * W + x, r = hash(x, y);
    COL.setHSL(0.08 + r * 0.02, 0.1 + r * 0.05, 0.06 + r * 0.03 + (r > 0.94 ? 0.02 : 0));
    gBase.set([COL.r, COL.g, COL.b], i * 3);
    M4.makeTranslation(wx(x), -0.12 - r * 0.025, wz(y));
    ground.setMatrixAt(i, M4);
    ground.setColorAt(i, COL);
  }
  root.add(ground);
  // 받침돌과 가장자리 석축
  const frameM = std(0x2a1e14, {roughness: 0.95});
  mesh(root, new THREE.BoxGeometry(W + 1.6, 2, 0.8), frameM, 0, -1.25, -H / 2 - 0.4, false);
  mesh(root, new THREE.BoxGeometry(W + 1.6, 2, 0.8), frameM, 0, -1.25, H / 2 + 0.4, false);
  mesh(root, new THREE.BoxGeometry(0.8, 2, H), frameM, -W / 2 - 0.4, -1.25, 0, false);
  mesh(root, new THREE.BoxGeometry(0.8, 2, H), frameM, W / 2 + 0.4, -1.25, 0, false);
  mesh(root, new THREE.PlaneGeometry(W, H).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({color: 0x000000}), 0, -2.2, 0, false);
  const curbM = std(0x5a4632, {roughness: 0.9});
  for (let i = -1; i <= W; i++) for (const j of [-1, H]) mesh(root, new RoundedBoxGeometry(0.96, 0.22 + hash(i, j) * 0.12, 0.6, 2, 0.04), curbM, wx(i), 0, wz(j) + (j < 0 ? 0.2 : -0.2));
  for (let j = 0; j < H; j++) for (const i of [-1, W]) mesh(root, new RoundedBoxGeometry(0.6, 0.22 + hash(i, j) * 0.12, 0.96, 2, 0.04), curbM, wx(i) + (i < 0 ? 0.2 : -0.2), 0, wz(j));
  // 네 모서리 화로 기둥
  const braziers = [];
  for (const [i, j] of [[-1, -1], [W, -1], [-1, H], [W, H]]) {
    const b = new THREE.Group();
    b.position.set(wx(i), 0, wz(j));
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
    root.add(b);
    braziers.push({fl, L});
  }

  const wallCells = [];
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (rows[y][x] === '#') wallCells.push([x, y]);
  const nW = Math.max(1, wallCells.length);
  const wall = new THREE.InstancedMesh(new RoundedBoxGeometry(0.9, 1, 0.9, 2, 0.05), std(0xffffff, {roughness: 0.88}), nW);
  const cap = new THREE.InstancedMesh(new RoundedBoxGeometry(1, 0.14, 1, 2, 0.04), std(0xffffff, {roughness: 0.8}), nW);
  wall.castShadow = cap.castShadow = true; wall.receiveShadow = cap.receiveShadow = true;
  const wBase = new Float32Array(wallCells.length * 3), cBase = new Float32Array(wallCells.length * 3);
  wallCells.forEach(([x, y], k) => {
    const r = hash(x, y), ruin = hash(y + 17, x + 3) < 0.25, h = ruin ? 0.35 + r * 0.3 : 0.85 + r * 0.6;
    const rot = Q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), (r - 0.5) * (ruin ? 0.6 : 0.12));
    COL.setHSL(0.075 + r * 0.02, 0.2, 0.17 + r * 0.06);
    wBase.set([COL.r, COL.g, COL.b], k * 3);
    M4.compose(V3.set(wx(x), h / 2, wz(y)), rot, S3.set(1, h, 1));
    wall.setMatrixAt(k, M4); wall.setColorAt(k, COL);
    COL.setHSL(0.085 + r * 0.02, 0.24, 0.26 + r * 0.07);
    cBase.set([COL.r, COL.g, COL.b], k * 3);
    M4.compose(V3.set(wx(x) + (ruin ? (r - 0.5) * 0.2 : 0), h + 0.05, wz(y)), rot, S3.set(ruin ? 0.8 : 1, 1, ruin ? 0.8 : 1));
    cap.setMatrixAt(k, M4); cap.setColorAt(k, COL);
  });
  wall.count = cap.count = wallCells.length;
  root.add(wall, cap);

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
    lbl.position.set(0, 0.7, 0); lbl.scale.set(0.05, 0.026, 1); lbl.renderOrder = 14;
    grp.add(lbl);
    grp.userData.cs = cs; grp.userData.glint = glint; grp.userData.glow = glow; grp.userData.lbl = lbl;
    root.add(grp);
    ore.set(x + ',' + y, grp);
  }

  // 구덩이
  const traps = new Map();
  const ringGeo = new THREE.RingGeometry(0.22, 0.3, 28).rotateX(-Math.PI / 2);
  const shaftG = new THREE.CylinderGeometry(0.69, 0.6, 2.1, 4, 1, true).rotateY(Math.PI / 4);
  const shaftM = new THREE.MeshBasicMaterial({map: shaftTex(), side: THREE.BackSide});
  const rimM = std(0x4a3a28, {roughness: 0.95});
  for (const [x, y] of R.map.traps) {
    const hidden = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({color: 0xe5533f, transparent: true, opacity: 0.6, depthWrite: false}));
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
    root.add(hidden, rev);
    traps.set(x + ',' + y, {hidden, rev, gi: y * W + x, gy: -0.12 - hash(x, y) * 0.025});
  }

  // 야영지
  const bases = R.map.bases.map(([x, y], t) => {
    const b = makeBase(t);
    b.g.position.set(wx(x), 0, wz(y));
    b.g.rotation.y = Math.atan2(W / 2 - 0.5 - x, H / 2 - 0.5 - y);
    root.add(b.g);
    return b;
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

  world = {revN: -1, root, ground, gBase, wall, cap, wallCells, wBase, cBase, braziers, ore, traps, bases, mind, paths, sel, units: new Map(), fogKey: '', mindKey: ''};
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
  const s = Math.max(W, H);
  camera.position.set(0, s * 0.95, s * 0.78);
  controls.target.set(0, 0, 0.6);
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
  e = {atk: new Map(), hit: new Map(), mine: new Set(), die: new Map(), list: F[g].e || []};
  for (const v of e.list) {
    if (v[0] === 'atk') { e.atk.set(v[1], v); e.hit.set(v[6], v); }
    else if (v[0] === 'mine') e.mine.add(v[1]);
    else if (v[0] === 'die') e.die.set(v[1], v);
  }
  evCache.set(g, e);
  return e;
}

function applyFog(fi, team, vis, seen) {
  const key = fi + '|' + team;
  if (key === world.fogKey) return;
  world.fogKey = key;
  const fac = i => !vis ? 1 : vis[i] ? 1 : seen[i] ? 0.4 : 0.09;
  for (let i = 0; i < W * H; i++) {
    const k = fac(i);
    COL.setRGB(world.gBase[i * 3] * k, world.gBase[i * 3 + 1] * k, world.gBase[i * 3 + 2] * k);
    world.ground.setColorAt(i, COL);
  }
  world.ground.instanceColor.needsUpdate = true;
  world.wallCells.forEach(([x, y], j) => {
    const k = fac(y * W + x);
    COL.setRGB(world.wBase[j * 3] * k, world.wBase[j * 3 + 1] * k, world.wBase[j * 3 + 2] * k);
    world.wall.setColorAt(j, COL);
    COL.setRGB(world.cBase[j * 3] * k, world.cBase[j * 3 + 1] * k, world.cBase[j * 3 + 2] * k);
    world.cap.setColorAt(j, COL);
  });
  if (world.wall.instanceColor) world.wall.instanceColor.needsUpdate = true;
  if (world.cap.instanceColor) world.cap.instanceColor.needsUpdate = true;
}

function updateStatic(fi, team, seen, now) {
  const om = oreAt[fi];
  for (const [k, grp] of world.ore) {
    const amt = om.get(k) || 0;
    const [x, y] = k.split(',').map(Number);
    grp.visible = amt > 0 && (!seen || seen[y * W + x] === 1);
    if (!grp.visible) continue;
    const cs = grp.userData.cs, n = Math.max(1, Math.ceil(Math.min(1, amt / 16) * cs.length));
    if (grp.userData.amt !== amt) { grp.userData.amt = amt; grp.userData.lbl.material.map = numTex(amt); grp.userData.lbl.material.needsUpdate = true; }
    cs.forEach((c, i) => c.visible = i < n);
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
    const r = rev.has(k);
    t.hidden.visible = !r && team < 0 && showTraps;
    t.rev.visible = r && (!seen || seen[y * W + x] === 1);
    if (changed) { M4.makeTranslation(wx(x), t.gy, wz(y)); if (r) M4.scale(S3.set(0.001, 0.001, 0.001)); world.ground.setMatrixAt(t.gi, M4); }
    if (t.rev.visible) pitWind(wx(x), wz(y), now, x * 31 + y);
  }
  if (changed) world.ground.instanceMatrix.needsUpdate = true;
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
    if (hit && a > 0.45) shake = (1 - a) * 0.05;
    b.g.position.x = wx(x) + Math.sin(now * 70) * shake;
    for (const m of b.flash) m.emissive.setRGB(shake * 12, 0, 0);
    if (t === 0) for (const [k, br] of world.braziers.entries()) { const f2 = 1 + Math.sin(now * 11 + k * 2) * 0.1 + Math.sin(now * 19 + k) * 0.06; br.fl.scale.set(1, f2, 1); br.L.intensity = 9 * f2; }
    setHp(b.hp, hp / R.const.hp.B, TC[t].c);
    billboard(b.hp, b.g);
  });
}

function updateUnits(f, g, a, fi, team, vis, now) {
  const moving = g !== f, ev = evOf(g);
  for (const o of world.units.values()) o.g.visible = false;
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
      world.units.set(u[0], o);
      o.g.rotation.y = Math.atan2(W / 2 - u[3], H / 2 - u[4]);
    }
    return o;
  };
  for (const u of F[g].u) {
    const id = u[0], p = A.get(id), o = getU(u);
    let x = u[3], y = u[4], st = 'idle';
    const atk = moving ? ev.atk.get(id) : null;
    if (moving && p && (p[3] !== u[3] || p[4] !== u[4])) {
      const e = ease(a);
      x = p[3] + (u[3] - p[3]) * e; y = p[4] + (u[4] - p[4]) * e;
      st = 'walk';
      o.face = Math.atan2(u[3] - p[3], u[4] - p[4]);
    } else if (atk) {
      st = 'attack';
      o.face = Math.atan2(atk[4] - atk[2], atk[5] - atk[3]);
    } else if (moving && ev.mine.has(id)) st = 'mine';
    if (!show(o, x, y, u[1] === team)) continue;
    if (o.face !== null) o.g.rotation.y = lerpAng(o.g.rotation.y, o.face, 0.3);
    pose(o, st, a, now, id);
    for (const fl of o.flames) fl.scale.set(1, 1 + Math.sin(now * 17 + id) * 0.18, 1);
    const sc = moving && !p ? elastic(Math.min(1, a * 1.3)) : 1;
    o.g.scale.setScalar(Math.max(0.001, sc) * CH * (o.kind === 'G' ? 1.12 : 1));
    o.disc.visible = o.badge.visible = true;
    const src = moving && a < 0.5 && p ? p : u;
    o.pips.forEach((pp, i) => pp.visible = i < src[6]);
    if (o.kind === 'E' && o._carry !== src[6]) { o._carry = src[6]; o.badge.material.map = badgeTex('E', o.team, src[6]); o.badge.material.needsUpdate = true; }
    const mx = R.const.hp[u[2]];
    o.hp.visible = src[5] < mx;
    setHp(o.hp, src[5] / mx, TC[u[1]].c);
    billboard(o.hp, o.g);
    const hit = moving && ev.hit.get(id);
    setFlash(o, hit && a > 0.45 ? Math.max(0, 1 - (a - 0.45) / 0.4) : 0);
    if (hit && a > 0.45 && a < 0.8) {            // 맞으면 뒤로 밀림
      const dx = u[3] - hit[2], dy = u[4] - hit[3], d = Math.hypot(dx, dy) || 1, k = Math.sin(Math.PI * (a - 0.45) / 0.35) * 0.12;
      o.g.position.x += dx / d * k; o.g.position.z += dy / d * k;
    }
    if (u[7] && (team < 0 || u[1] === team)) breeze(o.g.position, now, id, Math.round(x), Math.round(y));
  }
  if (!moving) return;
  for (const u of F[f].u) {                       // 이번 라운드에 죽은 유닛
    if (B.has(u[0])) continue;
    const o = getU(u), d = ev.die.get(u[0]);
    let x = u[3], y = u[4];
    const trap = d && d[4] === 'trap';
    if (d && trap) { const e = ease(Math.min(1, a * 2.5)); x = u[3] + (d[2] - u[3]) * e; y = u[4] + (d[3] - u[4]) * e; }
    if (!show(o, x, y, u[1] === team)) continue;
    o.hp.visible = false; o.disc.visible = o.badge.visible = false;
    setFlash(o, 0);
    if (trap) {                                    // 구덩이 속으로 빨려 떨어진다
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
function makeArrow() {
  const g = new THREE.Group();
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.5, 6), new THREE.MeshStandardMaterial({color: 0xd9c29a}));
  shaft.rotation.x = Math.PI / 2; g.add(shaft);
  const head = new THREE.Mesh(new THREE.ConeGeometry(0.035, 0.1, 6), new THREE.MeshBasicMaterial({color: 0xffffff}));
  head.rotation.x = Math.PI / 2; head.position.z = 0.29; g.add(head);
  for (const r of [0, Math.PI / 2]) { const f = new THREE.Mesh(new THREE.PlaneGeometry(0.1, 0.05), new THREE.MeshBasicMaterial({color: 0xf2ead8, side: THREE.DoubleSide})); f.rotation.set(0, Math.PI / 2, r); f.position.z = -0.22; g.add(f); }
  const trail = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.03, 0.9, 6), addMat(0xffe2a0, 0.4));
  trail.rotation.x = Math.PI / 2; trail.position.z = -0.7; g.add(trail);
  g.userData = {head, trail};
  return g;
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
    m.rotation.set(t * 9 + k, t * 7, 0);
  }
}
const texCache = new Map();
function textSprite(str, color) {
  const key = str + color;
  let tex = texCache.get(key);
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

function effects(g, a, canSee) {
  const baseIdx = id => R.map.base_ids.indexOf(id);
  for (const e of evOf(g).list) {
    const k = e[0];
    if (k === 'atk') {
      const [, id, ax, ay, tx, ty] = e;
      if (!canSee(ax, ay) && !canSee(tx, ty)) continue;
      const u = umap[g].get(id) || umap[Math.max(0, g - 1)].get(id), bi = baseIdx(id), col = u ? TC[u[1]].l : bi >= 0 ? TC[bi].l : 0xffffff;
      if (a > 0.28 && a < 0.5) {                 // 화살이 날아간다
        const m = fx('arrow', makeArrow);
        const q = (a - 0.28) / 0.22, x0 = wx(ax), z0 = wz(ay), x1 = wx(tx), z1 = wz(ty), y0 = bi >= 0 ? 1.0 : 0.75;
        m.position.set(x0 + (x1 - x0) * q, y0 + (0.5 - y0) * q + Math.sin(Math.PI * q) * 0.25, z0 + (z1 - z0) * q);
        m.lookAt(x1, 0.5, z1);
        m.userData.head.material.color.setHex(col);
      }
      if (a > 0.5) {
        const q = (a - 0.5) / 0.5;
        burst(wx(tx), wz(ty), 0.5, 8, 0xffffff, q, 1.6, id * 31 + g, 3, 0.8);
        ring(wx(tx), wz(ty), 0.5, 0.15 + q * 0.5, col, 1 - q);
      }
    } else if (k === 'trap') {
      const [, id, x, y] = e;
      if (!canSee(x, y) || a < 0.35) continue;
      const q = (a - 0.35) / 0.65;                  // 무너지는 흙먼지
      ring(wx(x), wz(y), 0.04, 0.3 + q * 1.2, 0xb89a70, 0.7 * (1 - q));
      burst(wx(x), wz(y), 0.05, 16, 0xa88a60, q, 1.6, id * 17 + g, -1.2, 1.6);
    } else if (k === 'die') {
      const [id, x, y, cause] = [e[1], e[2], e[3], e[4]];
      if (!canSee(x, y)) continue;
      const bi = baseIdx(id);
      if (bi >= 0) {
        const m = fx('flash', () => new THREE.Mesh(sphG, addMat(0xff8030)));
        m.position.set(wx(x), 0.6, wz(y)); m.scale.setScalar(0.3 + easeOut(a) * 2); m.material.opacity = 1 - a;
        m.material.color.setHex(TC[bi].c);
        burst(wx(x), wz(y), 0.5, 40, 0xffd080, a, 5, id + g, 6, 2);
      } else if (cause === 'atk' && a > 0.5) {
        burst(wx(x), wz(y), 0.3, 12, 0xd8dce6, (a - 0.5) * 2, 1.4, id * 13 + g, 3, 1);
      }
    } else if (k === 'mine') {
      const [, id, x, y] = e;
      if (!canSee(x, y) || a < 0.5) continue;
      burst(wx(x), wz(y), 0.15, 7, 0xffd84a, (a - 0.5) * 2, 1.6, id * 7 + g, 5, 0.8);
    } else if (k === 'dlv') {
      const [, id, amt, x, y] = e;
      if (!canSee(x, y)) continue;
      const s = textSprite('+' + amt, '#ffd978');
      s.position.set(wx(x), 1.1 + a * 0.9, wz(y)); s.scale.set(0.9, 0.45, 1); s.material.opacity = 1 - a * a;
    } else if (k === 'spawn') {
      const [, id, t, kd, x, y] = e;
      if (!canSee(x, y)) continue;
      const m = fx('pillar', () => new THREE.Mesh(pillarG, addMat(0xffffff)));
      m.position.set(wx(x), 1.1, wz(y)); m.material.color.setHex(TC[t].c); m.material.opacity = 0.7 * (1 - a);
      m.scale.set(1 - a * 0.6, 1, 1 - a * 0.6);
      ring(wx(x), wz(y), 0.03, 0.3 + a * 0.4, TC[t].l, 1 - a);
    }
  }
}

// ---------------- 한 장면 그리기 ----------------
function frame(f, g, a, fi, team, vis, seen) {
  if (!world) build();
  if (!world) return;
  const now = performance.now() / 1000, moving = g !== f;
  const canSee = (x, y) => !vis || vis[y * W + x] === 1;
  fxBegin();
  applyFog(fi, team, vis, seen);
  updateStatic(fi, team, seen, now);
  updateBases(fi, g, a, moving, seen, vis, now);
  updateUnits(f, g, a, fi, team, vis, now);
  updateMind(fi, team);
  if (moving) effects(g, a, canSee);
  // 선택 고리
  let sx = null, sy = null;
  if (selId != null) {
    const bi = R.map.base_ids.indexOf(selId);
    if (bi >= 0) [sx, sy] = R.map.bases[bi];
    else { const o = world.units.get(selId); if (o && o.g.visible) { sx = o.x; sy = o.y; } }
  }
  world.sel.visible = sx !== null;
  if (sx !== null) {
    world.sel.position.set(wx(sx), 0.02, wz(sy));
    world.sel.material.opacity = 0.6 + 0.4 * Math.sin(now * 5);
    world.sel.scale.setScalar(selId === R.map.base_ids[0] || selId === R.map.base_ids[1] ? 1.25 : 1);
  }
  controls.update();
  composer.render();
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
renderer.domElement.addEventListener('pointerup', ev => {
  if (down && Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) < 5) { const c = cellOf(ev); if (c) selectCell(c[0], c[1]); }
  down = null;
});
renderer.domElement.addEventListener('pointermove', ev => { const c = cellOf(ev); if (c) hoverCell(c[0], c[1]); });

function focus(x, y, d) {
  controls.target.set(wx(x), 0, wz(y));
  camera.position.set(wx(x), d * 0.75, wz(y) + d * 0.65);
  controls.update();
}

window.View3D = {build, frame, resize, resetCam, focus};
if (window.onView3DReady) window.onView3DReady();
