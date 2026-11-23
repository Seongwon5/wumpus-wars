# three.js 묶음

`three.bundle.min.js` 는 [three.js](https://threejs.org) 0.160.0 (MIT 라이선스) 과 뷰어가 쓰는 부가 모듈을 한 파일로 묶은 것이다.
리플레이 html 안에 그대로 들어가므로 인터넷 없이도 3D 화면이 열린다.

다시 만들기 (Node.js 필요):

```bash
npm install three@0.160.0 esbuild
npx esbuild entry.js --bundle --format=iife --global-name=__three --minify --legal-comments=none \
    --alias:three/addons=./node_modules/three/examples/jsm --outfile=three.bundle.min.js
```

`entry.js`:

```js
export * as THREE from 'three';
export {OrbitControls} from 'three/addons/controls/OrbitControls.js';
export {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';
export {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
export {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
export {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
export {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
```
