import { useEffect, useRef } from 'react';

// Облака над картой после загрузки: фрактальный шум в фрагментном шейдере. Пока open = false,
// облака плотные и медленно плывут; при open они расходятся от центра к краям и открывают карту.
// Холст рисуется в половинном разрешении и живёт только до конца анимации.

const VERT = `attribute vec2 p; varying vec2 uv; void main(){ uv = p * 0.5 + 0.5; gl_Position = vec4(p, 0.0, 1.0); }`;

const FRAG = `
precision mediump float;
varying vec2 uv;
uniform float t;
uniform float open;
uniform vec2 res;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 6; i++){ v += a * noise(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
  return v;
}
void main(){
  vec2 c = uv - 0.5;
  c.x *= res.x / res.y;
  float r = length(c);
  vec2 dir = r > 0.0001 ? c / r : vec2(0.0);
  // облака уходят от центра и чуть приближаются: будто камера проходит сквозь них
  vec2 q = c * (1.0 - 0.35 * open) - dir * open * 0.9;
  vec2 drift = vec2(t * 0.018, t * 0.006);
  float d = fbm(q * 1.8 + drift);
  float detail = fbm(q * 4.2 - drift * 1.5);
  // до раскрытия облака сплошные; при раскрытии сначала редеет центр, края держатся дольше
  float cover = 0.95 + 0.12 * detail - open * 1.45 + r * open * 1.0;
  float a = smoothstep(0.34, 0.58, d + cover - 0.5);
  float shade = fbm(q * 1.8 + drift + vec2(-0.05, 0.06)) - d;
  vec3 shadow = vec3(0.56, 0.62, 0.72);
  vec3 lit = vec3(0.97, 0.98, 1.0);
  vec3 col = mix(shadow, lit, clamp(0.72 + shade * 3.0 + (detail - 0.5) * 0.35, 0.0, 1.0));
  gl_FragColor = vec4(col * a, a);
}`;

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  return s;
}

const OPEN_MS = 2200;

export function CloudReveal({ open, onDone }: { open: boolean; onDone: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const openAt = useRef<number | null>(null);
  const doneRef = useRef(onDone);

  useEffect(() => {
    doneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (open && openAt.current == null) openAt.current = performance.now();
  }, [open]);

  useEffect(() => {
    const el = canvas.current;
    const gl = el?.getContext('webgl', { premultipliedAlpha: true, antialias: false, alpha: true });
    if (!el || !gl) {
      doneRef.current();
      return;
    }
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const uT = gl.getUniformLocation(prog, 't');
    const uOpen = gl.getUniformLocation(prog, 'open');
    const uRes = gl.getUniformLocation(prog, 'res');
    const start = performance.now();
    let raf = 0;

    const resize = () => {
      el.width = Math.max(1, Math.floor(window.innerWidth / 2));
      el.height = Math.max(1, Math.floor(window.innerHeight / 2));
      gl.viewport(0, 0, el.width, el.height);
    };
    resize();
    window.addEventListener('resize', resize);

    const frame = (now: number) => {
      const o = openAt.current == null ? 0 : Math.min((now - openAt.current) / OPEN_MS, 1);
      const eased = o < 0.5 ? 4 * o * o * o : 1 - (-2 * o + 2) ** 3 / 2;
      gl.uniform1f(uT, (now - start) / 1000);
      gl.uniform1f(uOpen, eased);
      gl.uniform2f(uRes, el.width, el.height);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (o >= 1) {
        doneRef.current();
        return;
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
  }, []);

  return (
    <canvas
      ref={canvas}
      aria-hidden="true"
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', zIndex: 40, pointerEvents: 'none' }}
    />
  );
}
