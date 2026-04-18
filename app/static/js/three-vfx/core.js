import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { BokehPass } from 'three/addons/postprocessing/BokehPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { ColorGradeShader } from './shaders.js';

export class ThreeVfxRuntime {
  constructor({ canvas, sceneKey }) {
    this.THREE = THREE;
    this.canvas = canvas;
    this.sceneKey = sceneKey;
    this.clock = new THREE.Clock();
    this.scene = new THREE.Scene();
    this.scene.background = null;
    this.scene.fog = new THREE.FogExp2(0x050814, 0.035);
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 120);
    this.profile = this.createProfile();
    this.pointer = new THREE.Vector2(0, 0);
    this.pointerTarget = new THREE.Vector2(0, 0);
    this.scroll = { y: window.scrollY || 0, progress: 0 };
    this.controller = null;
    this.animationFrame = null;
    this.isDragging = false;
    this.lastPointer = { x: 0, y: 0 };
  }

  createProfile() {
    const mobile = window.matchMedia('(max-width: 760px)').matches;
    const coarse = window.matchMedia('(pointer: coarse)').matches;
    return {
      mobile,
      coarse,
      pixelRatio: mobile ? 1.18 : 1.65,
      particleScale: mobile ? 0.34 : 1,
      bloomStrength: mobile ? 0.45 : 0.95,
      dof: !mobile,
      shadows: !mobile,
    };
  }

  init(sceneFactory) {
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      alpha: true,
      antialias: !this.profile.mobile,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.profile.pixelRatio));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.08;
    this.renderer.shadowMap.enabled = this.profile.shadows;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();

    this.addBaseLights();
    this.controller = sceneFactory(this);
    this.resize();
    this.composer = this.createComposer();
    this.bindEvents();
    document.body.classList.add('three-webgl-ready');
    this.tick();
  }

  addBaseLights() {
    const ambient = new THREE.AmbientLight(0xb8c7ff, 0.52);
    this.scene.add(ambient);

    const key = new THREE.DirectionalLight(0xffffff, 1.65);
    key.position.set(3.5, 5.2, 4.6);
    key.castShadow = this.profile.shadows;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.near = 0.5;
    key.shadow.camera.far = 30;
    this.scene.add(key);

    const rim = new THREE.PointLight(0x67d8ff, 2.2, 18);
    rim.position.set(-3.8, 2.2, 3.2);
    this.scene.add(rim);

    const gold = new THREE.PointLight(0xffd66b, 1.8, 14);
    gold.position.set(3.2, 1.4, 2.2);
    this.scene.add(gold);
  }

  createComposer() {
    const composer = new EffectComposer(this.renderer);
    composer.addPass(new RenderPass(this.scene, this.camera));

    const bloom = new UnrealBloomPass(
      new THREE.Vector2(window.innerWidth, window.innerHeight),
      this.profile.bloomStrength,
      this.profile.mobile ? 0.44 : 0.68,
      this.profile.mobile ? 0.82 : 0.58,
    );
    composer.addPass(bloom);

    if (this.profile.dof) {
      const bokeh = new BokehPass(this.scene, this.camera, {
        focus: 5.4,
        aperture: 0.00018,
        maxblur: 0.008,
      });
      composer.addPass(bokeh);
    }

    const grade = new ShaderPass(ColorGradeShader);
    grade.uniforms.saturation.value = this.profile.mobile ? 1.04 : 1.12;
    grade.uniforms.contrast.value = this.profile.mobile ? 1.02 : 1.08;
    grade.uniforms.tint.value = new THREE.Vector3(0.93, 0.98, 1.08);
    composer.addPass(grade);

    return composer;
  }

  bindEvents() {
    this.onResize = () => this.resize();
    this.onPointerMove = (event) => {
      const x = (event.clientX / Math.max(1, window.innerWidth)) * 2 - 1;
      const y = -(event.clientY / Math.max(1, window.innerHeight)) * 2 + 1;
      this.pointerTarget.set(x, y);
      if (this.isDragging && this.controller?.onDrag) {
        this.controller.onDrag({
          dx: event.clientX - this.lastPointer.x,
          dy: event.clientY - this.lastPointer.y,
          runtime: this,
        });
      }
      this.lastPointer = { x: event.clientX, y: event.clientY };
      this.controller?.onPointerMove?.({ x, y, event, runtime: this });
    };
    this.onPointerDown = (event) => {
      this.isDragging = true;
      this.lastPointer = { x: event.clientX, y: event.clientY };
      this.controller?.onPointerDown?.({ event, runtime: this });
    };
    this.onPointerUp = (event) => {
      this.isDragging = false;
      this.controller?.onPointerUp?.({ event, runtime: this });
    };
    this.onClick = (event) => {
      this.controller?.onClick?.({ event, runtime: this });
    };
    this.onScroll = () => {
      const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      this.scroll.y = window.scrollY || 0;
      this.scroll.progress = this.scroll.y / max;
      this.controller?.onScroll?.({ runtime: this, scroll: this.scroll });
    };

    window.addEventListener('resize', this.onResize, { passive: true });
    window.addEventListener('pointermove', this.onPointerMove, { passive: true });
    window.addEventListener('pointerdown', this.onPointerDown, { passive: true });
    window.addEventListener('pointerup', this.onPointerUp, { passive: true });
    window.addEventListener('click', this.onClick, { passive: true });
    window.addEventListener('scroll', this.onScroll, { passive: true });
  }

  resize() {
    const width = Math.max(1, window.innerWidth);
    const height = Math.max(1, window.innerHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    if (this.renderer) this.renderer.setSize(width, height, false);
    if (this.composer) this.composer.setSize(width, height);
  }

  tick() {
    const delta = Math.min(0.05, this.clock.getDelta());
    const time = this.clock.elapsedTime;
    this.pointer.lerp(this.pointerTarget, 0.07);
    this.controller?.update?.({ runtime: this, time, delta, pointer: this.pointer, scroll: this.scroll });
    if (this.composer) this.composer.render(delta);
    else this.renderer.render(this.scene, this.camera);
    this.animationFrame = window.requestAnimationFrame(() => this.tick());
  }

  dispose() {
    cancelAnimationFrame(this.animationFrame);
    window.removeEventListener('resize', this.onResize);
    window.removeEventListener('pointermove', this.onPointerMove);
    window.removeEventListener('pointerdown', this.onPointerDown);
    window.removeEventListener('pointerup', this.onPointerUp);
    window.removeEventListener('click', this.onClick);
    window.removeEventListener('scroll', this.onScroll);
    this.controller?.dispose?.();
    this.renderer?.dispose?.();
  }
}

export function canRunWebGL() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
  } catch (_) {
    return false;
  }
}
