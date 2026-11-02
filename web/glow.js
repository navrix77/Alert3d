/* Шейдерний шар «Тривоги»: світіння цілей (адитивний bloom) і сонарні хвилі від тих, що загрожують дому.
   Працює як custom layer MapLibre (WebGL), без сторонніх бібліотек. Дані кладе app.js у window.GLOW. */
(function () {
  const VS = `
    attribute vec2 a_merc; attribute vec2 a_corner; attribute vec4 a_col; attribute vec2 a_sz;
    uniform mat4 u_m; uniform vec2 u_vp;
    varying vec2 v_uv; varying vec4 v_col; varying float v_ring;
    void main(){
      vec4 p = u_m * vec4(a_merc, 0.0, 1.0);
      p.xy += a_corner * a_sz.x / u_vp * 2.0 * p.w;
      gl_Position = p; v_uv = a_corner; v_col = a_col; v_ring = a_sz.y;
    }`;
  const FS = `
    precision mediump float;
    uniform float u_t;
    varying vec2 v_uv; varying vec4 v_col; varying float v_ring;
    void main(){
      float r = length(v_uv);
      if (r > 1.0) discard;
      float core = exp(-r * r * 9.0) * 0.9;            // яскраве ядро
      float halo = exp(-r * 3.2) * 0.35;                // м'який ореол
      float a = (core + halo) * v_col.a;
      if (v_ring > 0.5) {                               // дві сонарні хвилі, що розходяться
        for (int i = 0; i < 2; i++) {
          float ph = fract(u_t * 0.55 + float(i) * 0.5);
          float w = smoothstep(0.06, 0.0, abs(r - ph)) * (1.0 - ph);
          a += w * 0.9;
        }
      }
      gl_FragColor = vec4(v_col.rgb * a, a);
    }`;
  function sh(gl, type, src) { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }
  const C = [[-1, -1], [1, -1], [1, 1], [-1, -1], [1, 1], [-1, 1]];

  window.GlowLayer = {
    id: 'glow', type: 'custom', renderingMode: '2d',
    onAdd(map, gl) {
      this.map = map;
      const p = gl.createProgram();
      gl.attachShader(p, sh(gl, gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl, gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p);
      this.p = p; this.buf = gl.createBuffer(); this.t0 = performance.now();
      this.loc = { merc: gl.getAttribLocation(p, 'a_merc'), corner: gl.getAttribLocation(p, 'a_corner'), col: gl.getAttribLocation(p, 'a_col'), sz: gl.getAttribLocation(p, 'a_sz'),
        m: gl.getUniformLocation(p, 'u_m'), vp: gl.getUniformLocation(p, 'u_vp'), t: gl.getUniformLocation(p, 'u_t') };
    },
    render(gl, args) {
      const G = window.GLOW || [];
      if (!G.length) return;
      const m = (args && args.defaultProjectionData && args.defaultProjectionData.mainMatrix) || args;
      const data = new Float32Array(G.length * 6 * 10);
      let o = 0;
      for (const g of G) {
        const mc = maplibregl.MercatorCoordinate.fromLngLat({ lng: g.p[0], lat: g.p[1] }, 0);
        for (const c of C) { data.set([mc.x, mc.y, c[0], c[1], g.c[0], g.c[1], g.c[2], g.a, g.s, g.ring ? 1 : 0], o); o += 10; }
      }
      gl.useProgram(this.p);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
      const L = this.loc, S = 40;
      gl.enableVertexAttribArray(L.merc); gl.vertexAttribPointer(L.merc, 2, gl.FLOAT, false, S, 0);
      gl.enableVertexAttribArray(L.corner); gl.vertexAttribPointer(L.corner, 2, gl.FLOAT, false, S, 8);
      gl.enableVertexAttribArray(L.col); gl.vertexAttribPointer(L.col, 4, gl.FLOAT, false, S, 16);
      gl.enableVertexAttribArray(L.sz); gl.vertexAttribPointer(L.sz, 2, gl.FLOAT, false, S, 32);
      gl.uniformMatrix4fv(L.m, false, m);
      gl.uniform2f(L.vp, gl.drawingBufferWidth / devicePixelRatio, gl.drawingBufferHeight / devicePixelRatio);
      gl.uniform1f(L.t, (performance.now() - this.t0) / 1000);
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.disable(gl.DEPTH_TEST);
      gl.drawArrays(gl.TRIANGLES, 0, G.length * 6);
      (window.nxRepaint?nxRepaint(this.map):this.map.triggerRepaint());
    },
  };
})();
