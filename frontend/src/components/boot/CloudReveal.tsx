import { useEffect, useRef } from 'react';

// Облака над картой после загрузки, нарисованные как в мультфильме: круглые клубы с контуром, три полосы
// света, штриховка в тени и лёгкое дрожание линий с частотой 8 кадров в секунду. Два слоя клубов плывут
// с разной скоростью. Пока open = false, облака закрывают экран; при open клубы сдуваются от центра к краям
// и расходятся. Холст живёт только до конца анимации.

const VERT = `attribute vec2 p; varying vec2 uv; void main(){ uv = p * 0.5 + 0.5; gl_Position = vec4(p, 0.0, 1.0); }`;

const FRAG = `
#extension GL_OES_standard_derivatives : enable
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying vec2 uv;
uniform float t;
uniform float open;
uniform vec2 res;

const vec3 HI = vec3(0.965, 0.970, 0.980);
const vec3 MID = vec3(0.855, 0.878, 0.922);
const vec3 LOW = vec3(0.700, 0.742, 0.820);
const vec3 INK = vec3(0.400, 0.450, 0.550);
const vec3 LIGHT = vec3(-0.35, 0.70, 0.62);

vec2 hash2(vec2 p){
  p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
  return fract(sin(p) * 43758.5453);
}
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash2(i).x, b = hash2(i + vec2(1.0, 0.0)).x;
  float c = hash2(i + vec2(0.0, 1.0)).x, d = hash2(i + vec2(1.0, 1.0)).x;
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// Мультяшный свет: три полосы по нормали поверхности, штриховка в тени.
vec3 shade(vec3 n){
  float dif = dot(n, normalize(LIGHT));
  float lit = smoothstep(0.10, 0.16, dif);
  vec3 col = mix(LOW, MID, lit);
  col = mix(col, HI, smoothstep(0.62, 0.68, dif));
  float hatch = step(0.64, fract((gl_FragCoord.x + gl_FragCoord.y) / 6.0));
  return mix(col, INK, hatch * 0.2 * (1.0 - lit));
}

// Сдувание клуба по его положению на экране: сначала в центре, у краёв позже, к концу исчезают все.
float growAt(vec2 screen){
  float g = clamp(1.2 - open * 2.4 + length(screen) * open * 1.5, 0.0, 1.0);
  return g * (1.0 - smoothstep(0.7, 1.0, open));
}

// Слой облаков: в каждой клетке сетки один клуб-полушар. Высоты клубов сливаются мягким максимумом,
// поэтому соседние клубы образуют одно облако с бугристым контуром, а свет ложится на облако целиком:
// нормаль берётся из производных общей высоты по экрану.
// Слой увеличивается от центра экрана (zoom < 1), так облака разлетаются к краям, не искажаясь.
vec4 layer(vec2 c, float zoom, vec2 drift, float scale, float px, float seed, float tick, float density){
  vec2 g = (c * zoom + drift) * scale;
  vec2 i = floor(g), f = fract(g);
  float wob = (noise(g * 2.7 + vec2(tick * 3.1, tick * 1.7)) - 0.5) * 0.05;
  const float K = 9.0;
  float top = 0.0, sum = 0.0, depth = -1.0;
  for (int y = -1; y <= 1; y++){
    for (int x = -1; x <= 1; x++){
      vec2 o = vec2(float(x), float(y));
      if (hash2(i + o + seed + 53.1).y > density) continue;
      vec2 h = hash2(i + o + seed);
      vec2 center = o + 0.15 + 0.7 * h;
      // клуб не шире 1,13 клетки по горизонтали, иначе он вылезет за соседние клетки и даст шов
      float rad = (0.5 + 0.38 * h.y) * growAt(((i + center) / scale - drift) / zoom);
      if (rad < 0.02) continue;
      vec2 dv = (f - center) * vec2(0.78, 1.0);
      float d = length(dv) / rad + wob;
      depth = max(depth, (1.0 - d) * rad);
      if (d >= 1.0) continue;
      float hgt = rad * sqrt(1.0 - d * d);
      float next = max(top, hgt);
      // вес клуба плавно гаснет к его краю, иначе край спрятанного клуба рисует на облаке пунктирное кольцо
      sum = sum * exp(K * (top - next)) + smoothstep(0.0, 0.08, hgt) * exp(K * (hgt - next));
      top = next;
    }
  }
  float pxl = px * zoom * scale;
  float height = sum > 0.0 ? top + log(sum) / K : 0.0;
  // производные считаются для всех пикселей до любого выхода из функции, иначе на краях они не определены
  vec3 n = normalize(vec3(-dFdx(height) / pxl, -dFdy(height) / pxl, 1.0));
  if (depth <= 0.0) return vec4(0.0);
  float edge = depth / pxl;
  float a = clamp(edge + 0.5, 0.0, 1.0);
  vec3 col = mix(INK, shade(n), smoothstep(1.2, 2.2, edge));
  return vec4(col * a, a);
}

void main(){
  vec2 c = uv - 0.5;
  c.x *= res.x / res.y;
  float px = 1.0 / res.y;
  float tick = floor(t * 8.0);
  // камера проходит сквозь облака: ближний слой увеличивается быстрее дальнего
  vec4 back = layer(c, 1.0 - 0.3 * open, vec2(t * 0.010, t * 0.003), 2.0, px, 0.0, tick, 1.0);
  vec4 mid = layer(c, 1.0 - 0.45 * open, vec2(t * 0.016, -t * 0.002), 3.2, px, 17.0, tick + 0.3, 0.6);
  vec4 front = layer(c, 1.0 - 0.62 * open, vec2(t * 0.024, t * 0.002), 5.0, px, 41.0, tick + 0.6, 0.4);
  // под клубами тень плотного облака, пока облака закрыты
  float baseA = clamp((growAt(c) - 0.9) / 0.04, 0.0, 1.0);
  float hatch = step(0.64, fract((gl_FragCoord.x + gl_FragCoord.y) / 6.0));
  vec4 col = vec4(mix(LOW * 0.92, INK, hatch * 0.25) * baseA, baseA);
  col = back + col * (1.0 - back.a);
  col = mid + col * (1.0 - mid.a);
  col = front + col * (1.0 - front.a);
  gl_FragColor = col;
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
    gl.getExtension('OES_standard_derivatives');
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      // шейдер не собрался на этом GPU: заставку пропускаем, карта открывается сразу
      doneRef.current();
      return;
    }
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
      // контур рисованных облаков требует чёткости: плотность пикселей до 1,5, а не половина экрана
      const scale = Math.min(window.devicePixelRatio || 1, 1.5);
      el.width = Math.max(1, Math.floor(window.innerWidth * scale));
      el.height = Math.max(1, Math.floor(window.innerHeight * scale));
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
