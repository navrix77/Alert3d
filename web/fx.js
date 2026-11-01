/* «Тривога» FX — усі рухомі цілі одним WebGL-шаром: хвіст-комета, ореол, сонар загрози, тінь і спрайт.
   Карта при цьому не перераховує жодних даних щокадру — лише GPU-малювання ~60 кадр/с.
   app.js щокадру кладе в window.FX масив: {p:[lon,lat], sa:кут на екрані°, type, col:[r,g,b], weak, thr, sel, tail:[[lon,lat],...]} */
(function () {
  const VS = `
    attribute vec2 a_merc; attribute vec2 a_corner; attribute vec2 a_off; attribute float a_size; attribute float a_rot;
    attribute vec4 a_col; attribute float a_kind;
    uniform mat4 u_m; uniform vec2 u_vp; uniform float u_px;
    varying vec2 v_c; varying vec4 v_col; varying float v_kind;
    void main(){
      // усе лежить у площині карти: кут — географічний курс (0 = північ), розмір — у пікселях на поточному масштабі
      float c = cos(a_rot), s = sin(a_rot);
      vec2 k = vec2(a_corner.x * c + a_corner.y * s, a_corner.x * s - a_corner.y * c);
      vec2 m = a_merc + (k * a_size + a_off) * u_px;
      gl_Position = u_m * vec4(m, 0.0, 1.0); v_c = a_corner; v_col = a_col; v_kind = a_kind;
    }`;
  const FS = `
    precision mediump float;
    uniform float u_t; uniform sampler2D u_tex; uniform float u_pass;
    varying vec2 v_c; varying vec4 v_col; varying float v_kind;
    void main(){
      float r = length(v_c);
      if (v_kind < 0.5) {                       // ореол / крапля хвоста
        if (r > 1.0) discard;
        float a = (exp(-r * r * 6.0) * 0.85 + exp(-r * 2.6) * 0.25) * v_col.a;
        gl_FragColor = vec4(v_col.rgb * a, a);
      } else if (v_kind < 1.5) {                // сонар загрози: дві хвилі
        if (r > 1.0) discard;
        float a = 0.0;
        for (int i = 0; i < 2; i++) { float ph = fract(u_t * 0.5 + float(i) * 0.5);
          a += smoothstep(0.045, 0.0, abs(r - ph)) * (1.0 - ph); }
        a *= v_col.a; gl_FragColor = vec4(v_col.rgb * a, a);
      } else if (v_kind > 4.5) {                // радар навколо дому: кільця дальності + розгортка з шлейфом
        if (r > 1.0) discard;
        float ang = atan(v_c.x, v_c.y);
        float ph = mod(ang - u_t * 1.1, 6.2831853) / 6.2831853;
        float sweep = pow(1.0 - ph, 10.0) * 0.55 + smoothstep(0.012, 0.0, 1.0 - ph) * 0.6;
        float rings = 0.0;
        for (int i = 1; i <= 3; i++) rings += smoothstep(0.012, 0.0, abs(r - float(i) / 3.0)) * 0.28;
        float a = (sweep * (1.0 - r * 0.35) + rings) * v_col.a * smoothstep(1.0, 0.92, r) + exp(-r * r * 60.0) * 0.5 * v_col.a;
        gl_FragColor = vec4(v_col.rgb * a, a);
      } else if (v_kind < 2.5) {                // кільце вибору
        if (r > 1.0) discard;
        float a = smoothstep(0.08, 0.0, abs(r - 0.86)) * v_col.a;
        gl_FragColor = vec4(v_col.rgb * a, a);
      } else {                                  // спрайт (3) або його тінь (4)
        vec2 uv = vec2(v_c.x, -v_c.y) * 0.5 + 0.5;
        vec4 t = texture2D(u_tex, uv);
        if (v_kind > 3.5 && v_kind < 4.5) gl_FragColor = vec4(0.0, 0.0, 0.0, t.a * 0.5);
        else gl_FragColor = vec4(t.rgb * t.a, t.a) * v_col.a;
      }
    }`;
  const Q = [[-1, -1], [1, -1], [1, 1], [-1, -1], [1, 1], [-1, 1]];
  const F = 13; // floats per vertex
  function sh(gl, type, src) { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }

  const FX = {
    id: 'fx', type: 'custom', renderingMode: '2d',
    onAdd(map, gl) {
      this.map = map; this.gl = gl; this.t0 = performance.now(); this.tex = {};
      const p = gl.createProgram();
      gl.attachShader(p, sh(gl, gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl, gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p);
      this.p = p; this.buf = gl.createBuffer();
      const A = n => gl.getAttribLocation(p, n), U = n => gl.getUniformLocation(p, n);
      this.a = { merc: A('a_merc'), corner: A('a_corner'), off: A('a_off'), size: A('a_size'), rot: A('a_rot'), col: A('a_col'), kind: A('a_kind') };
      this.u = { m: U('u_m'), vp: U('u_vp'), t: U('u_t'), tex: U('u_tex'), px: U('u_px') };
      for (const t of Object.keys(window.TYPE_COLOR)) {
        const img = new Image(); img.onload = () => {
          const tx = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tx);
          gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          this.tex[t] = tx; map.triggerRepaint();
        };
        img.src = 'sprites/t-' + t + '.png';
      }
    },
    quads(list) { // list: [merc, size, rot, col4, kind, off]
      const d = new Float32Array(list.length * 6 * F); let o = 0;
      for (const q of list) for (const c of Q) {
        d[o++] = q[0]; d[o++] = q[1]; d[o++] = c[0]; d[o++] = c[1]; d[o++] = q[8] || 0; d[o++] = q[9] || 0; d[o++] = q[2]; d[o++] = q[3];
        d[o++] = q[4][0]; d[o++] = q[4][1]; d[o++] = q[4][2]; d[o++] = q[4][3]; d[o++] = q[5];
      }
      return d;
    },
    draw(gl, data, n) {
      const a = this.a, S = F * 4;
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buf); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STREAM_DRAW);
      gl.enableVertexAttribArray(a.merc); gl.vertexAttribPointer(a.merc, 2, gl.FLOAT, false, S, 0);
      gl.enableVertexAttribArray(a.corner); gl.vertexAttribPointer(a.corner, 2, gl.FLOAT, false, S, 8);
      gl.enableVertexAttribArray(a.off); gl.vertexAttribPointer(a.off, 2, gl.FLOAT, false, S, 16);
      gl.enableVertexAttribArray(a.size); gl.vertexAttribPointer(a.size, 1, gl.FLOAT, false, S, 24);
      gl.enableVertexAttribArray(a.rot); gl.vertexAttribPointer(a.rot, 1, gl.FLOAT, false, S, 28);
      gl.enableVertexAttribArray(a.col); gl.vertexAttribPointer(a.col, 4, gl.FLOAT, false, S, 32);
      gl.enableVertexAttribArray(a.kind); gl.vertexAttribPointer(a.kind, 1, gl.FLOAT, false, S, 48);
      gl.drawArrays(gl.TRIANGLES, 0, n * 6);
    },
    render(gl, args) {
      const L = window.FX || [], H = window.FXHOME, B = window.FXBEACONS || [];
      if (!L.length && !H && !B.length) return;
      const map = this.map, z = map.getZoom();
      const M = (args && args.defaultProjectionData && args.defaultProjectionData.mainMatrix) || args;
      const mc = p => { const m = maplibregl.MercatorCoordinate.fromLngLat({ lng: p[0], lat: p[1] }, 0); return [m.x, m.y]; };
      const spr = Math.max(13, Math.min(34, 5 + z * 3.1));      // напіврозмір спрайта, px
      const glow = [], top = [];
      const day = !!window.FXDAY;
      if (H) { // радар дому: радіус ~25 км у пікселях поточного масштабу
        const hm = mc(H.p), mpp = 40075016.686 * Math.cos(H.p[1] * Math.PI / 180) / (512 * Math.pow(2, z));
        const c = H.state === 'danger' ? [1, 0.23, 0.3] : H.state === 'watch' ? [1, 0.72, 0.2] : [0.2, 0.95, 0.55];
        glow.push([hm[0], hm[1], Math.max(40, 25000 / mpp), 0, [c[0], c[1], c[2], day ? 0.55 : 0.8], 5]);
        // світловий потік від кожної загрози до дому
        const tnow = performance.now() / 1000;
        for (const f of L) if (f.thr) { const tm = mc(f.p);
          for (let k = 0; k < 7; k++) { const u = (tnow * 0.45 + k / 7) % 1;
            glow.push([tm[0] + (hm[0] - tm[0]) * u, tm[1] + (hm[1] - tm[1]) * u, spr * 0.35, 0, [1, 0.3, 0.35, 0.8 * Math.sin(u * Math.PI)], 0]); } }
      }
      for (const b of B) { const bm = mc(b.p); // маяки місць пуску
        glow.push([bm[0], bm[1], spr * 1.2, 0, [1, 0.2, 0.25, 0.9], 0]);
        glow.push([bm[0], bm[1], spr * 4, 0, [1, 0.2, 0.25, 0.8], 1]); }
      for (const f of L) {
        const m = mc(f.p), c = f.col, a = f.weak ? 0.45 : 1;
        // хвіст: краплі світла вздовж пройденого шляху, тануть до кінця
        const T = f.tail || [], N = T.length;
        for (let i = 0; i < N; i++) { const k = 1 - i / N, tm = mc(T[i]);
          glow.push([tm[0], tm[1], spr * (0.25 + 0.55 * k), 0, [c[0], c[1], c[2], 0.55 * k * k * a], 0]); }
        glow.push([m[0], m[1], spr * 1.9, 0, [c[0], c[1], c[2], 0.75 * a], 0]);
        if (f.thr) glow.push([m[0], m[1], spr * 5.5, 0, [1, 0.24, 0.3, 0.95], 1]);
        if (f.sel) top.push([m[0], m[1], spr * 1.7, 0, [1, 1, 1, 0.9], 2, 0, 0]);
        f._m = m;
      }
      gl.useProgram(this.p);
      gl.uniformMatrix4fv(this.u.m, false, M);
      gl.uniform2f(this.u.vp, gl.drawingBufferWidth / devicePixelRatio, gl.drawingBufferHeight / devicePixelRatio);
      gl.uniform1f(this.u.px, 1 / (512 * Math.pow(2, z)));
      gl.uniform1f(this.u.t, (performance.now() - this.t0) / 1000);
      gl.disable(gl.DEPTH_TEST); gl.disable(gl.STENCIL_TEST); gl.enable(gl.BLEND);
      if (day) gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); else gl.blendFunc(gl.ONE, gl.ONE); // уночі — адитивне світло
      this.draw(gl, this.quads(glow), glow.length);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);        // тіні, спрайти, кільця
      gl.activeTexture(gl.TEXTURE0); gl.uniform1i(this.u.tex, 0);
      for (const f of L) {
        const tx = this.tex[f.type]; if (!tx) continue;
        gl.bindTexture(gl.TEXTURE_2D, tx);
        const r = (f.hd || 0) * Math.PI / 180, a = f.weak ? 0.6 : 1;
        const q = [[f._m[0], f._m[1], spr, r, [1, 1, 1, a], 4, 0, 0, spr * 0.12, spr * 0.18],
                   [f._m[0], f._m[1], spr, r, [1, 1, 1, a], 3]];
        this.draw(gl, this.quads(q), 2);
      }
      if (top.length) this.draw(gl, this.quads(top), top.length);
      map.triggerRepaint();
    },
  };
  window.FxLayer = FX;
})();
