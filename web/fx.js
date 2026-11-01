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
    uniform float u_t; uniform sampler2D u_tex; uniform float u_pass; uniform float u_tint;
    varying vec2 v_c; varying vec4 v_col; varying float v_kind;
    float h21(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    float vn(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
      return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y); }
    float fbm(vec2 p){ return vn(p) * 0.55 + vn(p * 2.1 + 1.7) * 0.3 + vn(p * 4.3 + 3.9) * 0.15; }
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
      } else if (v_kind > 5.5) {                // реактивний струмінь: ядро з «діамантами» Маха, турбулентний факел, мерехтіння
        float d = (0.95 - v_c.y) / 1.95;            // 0 — зріз сопла, 1 — кінець квадрата
        if (d < 0.0 || d > 1.0) discard;
        float sd = v_col.a * 37.0;
        float tt = u_t + sd;
        float fl = 0.5 + 0.5 * sin(tt * 31.0) * sin(tt * 17.3 + 1.3);
        float L = 0.78 + 0.14 * fl;                  // довжина факела «дихає»
        float q = d / L;
        float n1 = fbm(vec2(v_c.x * 7.0, d * 9.0 - tt * 16.0));
        float n2 = fbm(vec2(v_c.x * 13.0 + 3.1, d * 17.0 - tt * 27.0));
        float x = abs(v_c.x + (n1 - 0.5) * 0.10 * q);
        // зовнішній факел: від сопла трохи розширюється, далі звужується й рветься на язики
        float w = 0.17 * (1.0 + 0.9 * smoothstep(0.0, 0.35, q)) * pow(max(0.0, 1.0 - q), 0.75) * (0.75 + 0.55 * n2);
        float outer = smoothstep(w, w * 0.35, x) * smoothstep(1.0, 0.55, q + (n1 - 0.5) * 0.35);
        // гаряче ядро і ударні «діаманти» (майже нерухомі, лише тремтять)
        float wc = 0.075 * (1.0 - smoothstep(0.0, 0.5, q));
        float core = smoothstep(wc, wc * 0.2, x) * (1.0 - smoothstep(0.32, 0.5, q));
        float dia = pow(0.5 + 0.5 * cos(q * 34.0 - 0.6 + sin(tt * 40.0) * 0.25), 3.0) * smoothstep(0.55, 0.05, q) * smoothstep(0.05, 0.0, x - 0.05);
        vec3 cOut = mix(vec3(1.0, 0.62, 0.18), vec3(0.85, 0.12, 0.04), smoothstep(0.2, 0.9, q));
        vec3 col = cOut * outer * (0.75 + 0.5 * n2)
                 + vec3(1.0, 0.9, 0.7) * core * 0.85
                 + vec3(0.8, 0.88, 1.0) * dia * 1.4;
        float a = clamp(max(outer * 0.85, max(core, dia * 0.8)), 0.0, 1.0);
        gl_FragColor = vec4(col, a);
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
      } else {                                  // спрайт (3.0–3.4, дробова частина — крен) або його тінь (4)
        vec2 uv = vec2(v_c.x, -v_c.y) * 0.5 + 0.5;
        vec4 t = texture2D(u_tex, uv);
        if (v_kind > 3.5 && v_kind < 4.5) {     // м'яка тінь на землі
          float sa = t.a * 0.4;
          for (int i = 0; i < 6; i++) { float an = float(i) * 1.0472; sa += texture2D(u_tex, uv + vec2(cos(an), sin(an)) * 0.03).a * 0.1; }
          gl_FragColor = vec4(0.0, 0.0, 0.0, sa * 0.42 * v_col.a); return; }
        float bank = (v_kind - 3.0) / 0.4 * 2.0 - 1.0;
        // об'єм: нормаль з градієнта силуету (фаска по краях) + округлий фюзеляж + крен крил
        float e = 0.02;
        float ax = texture2D(u_tex, uv + vec2(e, 0.0)).a - texture2D(u_tex, uv - vec2(e, 0.0)).a;
        float ay = texture2D(u_tex, uv - vec2(0.0, e)).a - texture2D(u_tex, uv + vec2(0.0, e)).a;
        float fus = smoothstep(0.16, 0.0, abs(v_c.x));
        vec3 n = normalize(vec3(-ax * 1.6 - v_c.x * 2.6 * fus + bank * 0.45 * (1.0 - fus), -ay * 1.6, 1.0));
        vec3 L = normalize(vec3(-0.45, 0.55, 0.7));
        float dif = clamp(dot(n, L), 0.0, 1.0);
        float spec = pow(max(dot(reflect(-L, n), vec3(0.0, 0.0, 1.0)), 0.0), 22.0);
        float o = 0.0;
        for (int i = 0; i < 12; i++) { float an = float(i) * 0.5236;
          o = max(o, texture2D(u_tex, uv + vec2(cos(an), sin(an)) * 0.03).a); }
        float rim = clamp(o - t.a, 0.0, 1.0) * 0.85;
        vec3 body = t.rgb * (0.38 + 0.82 * dif) + vec3(spec * 0.75);
        // огляд країни: суцільний колір типу (читається з першого погляду); зблизька — реалістичний метал
        vec3 tc = v_col.rgb * (0.55 + 0.6 * dif) + vec3(spec * 0.35);
        body = mix(body, tc, u_tint);
        vec3 rimc = mix(v_col.rgb, vec3(0.03, 0.04, 0.06), u_tint * 0.85);
        float a = max(t.a, rim);
        gl_FragColor = vec4(body * t.a + rimc * rim, a) * v_col.a;
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
      this.u = { m: U('u_m'), vp: U('u_vp'), t: U('u_t'), tex: U('u_tex'), px: U('u_px'), tint: U('u_tint') };
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
      const spr = Math.max(9, Math.min(23, 3 + z * 2.1));       // напіврозмір спрайта, px (менші — як на радарі)
      const glow = [], top = [];
      const day = !!window.FXDAY;
      if (H) { // радар дому: радіус ~25 км у пікселях поточного масштабу
        const hm = mc(H.p), mpp = 40075016.686 * Math.cos(H.p[1] * Math.PI / 180) / (512 * Math.pow(2, z));
        const c = H.state === 'danger' ? [1, 0.23, 0.3] : H.state === 'watch' ? [1, 0.72, 0.2] : [0.2, 0.95, 0.55];
        const kz = Math.max(0, Math.min(1, (12.5 - z) / 1.5)); // зблизька радар не фарбує весь екран
        if (kz > 0) glow.push([hm[0], hm[1], Math.max(40, 25000 / mpp), 0, [c[0], c[1], c[2], (day ? 0.55 : 0.8) * kz], 5]);
        // світловий потік від кожної загрози до дому
        const tnow = performance.now() / 1000;
        for (const f of L) if (f.thr && Math.hypot(f.p[0] - H.p[0], (f.p[1] - H.p[1]) * 1.5) < 1.2) { const tm = mc(f.p);
          for (let k = 0; k < 7; k++) { const u = (tnow * 0.45 + k / 7) % 1;
            glow.push([tm[0] + (hm[0] - tm[0]) * u, tm[1] + (hm[1] - tm[1]) * u, spr * 0.35, 0, [1, 0.3, 0.35, 0.8 * Math.sin(u * Math.PI)], 0]); } }
      }
      for (const b of B) { const bm = mc(b.p); // маяки місць пуску
        glow.push([bm[0], bm[1], spr * 0.9, 0, [1, 0.2, 0.25, 0.7], 0]); }
      for (const f of L) {
        const m = mc(f.p), c = f.col, age = f.age || 0;
        // давність: старе повідомлення тьмяніє, а зона «де ціль може бути» росте — без вигаданого польоту
        const a = (f.weak ? 0.45 : 1) * (age > 300 ? Math.max(0.35, 1 - (age - 300) / 1800) : 1);
        if (age > 300 && f.spd && z >= 6.5) { const km = Math.min(45, f.spd * age / 3600 * 0.5), mpp = 40075016.686 * Math.cos(f.p[1] * Math.PI / 180) / (512 * Math.pow(2, z));
          const r = Math.max(spr * 1.6, km * 1000 / mpp); glow.push([m[0], m[1], r, 0, [c[0], c[1], c[2], 0.10], 0]); top.push([m[0], m[1], r, 0, [c[0], c[1], c[2], 0.22], 2, 0, 0]); }
        // хвіст: краплі світла вздовж пройденого шляху, тануть до кінця
        const T = f.tail || [], N = T.length;
        for (let i = 0; i < N; i++) { const k = 1 - i / N, tm = mc(T[i]);
          glow.push([tm[0], tm[1], spr * (0.2 + 0.4 * k), 0, [c[0], c[1], c[2], 0.35 * k * k * a], 0]); }
        glow.push([m[0], m[1], spr * (z < 6 ? 1.1 : 1.5), 0, [c[0], c[1], c[2], 0.45 * a], 0]);
        if (f.thr) glow.push([m[0], m[1], spr * (z < 6 ? 3 : 5.5), 0, [1, 0.24, 0.3, 0.95], 1]);
        if (f.sel) top.push([m[0], m[1], spr * 1.7, 0, [1, 1, 1, 0.9], 2, 0, 0]);
        f._m = m;
      }
      gl.useProgram(this.p);
      gl.uniformMatrix4fv(this.u.m, false, M);
      gl.uniform2f(this.u.vp, gl.drawingBufferWidth / devicePixelRatio, gl.drawingBufferHeight / devicePixelRatio);
      gl.uniform1f(this.u.px, 1 / (512 * Math.pow(2, z)));
      gl.uniform1f(this.u.t, (performance.now() - this.t0) / 1000);
      gl.uniform1f(this.u.tint, Math.max(0, Math.min(1, (8.5 - z) / 2)));
      gl.disable(gl.DEPTH_TEST); gl.disable(gl.STENCIL_TEST); gl.enable(gl.BLEND);
      if (day) gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); else gl.blendFunc(gl.ONE, gl.ONE); // уночі — адитивне світло
      this.draw(gl, this.quads(glow), glow.length);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);        // тіні, спрайти, кільця
      gl.activeTexture(gl.TEXTURE0); gl.uniform1i(this.u.tex, 0);
      const fl = [];
      for (const f of L) {
        const tx = this.tex[f.type]; if (!tx) continue;
        gl.bindTexture(gl.TEXTURE_2D, tx);
        // ціль «планує»: легке погойдування курсу з креном у бік повороту і повільна зміна висоти
        const ph = ((f.p[0] * 131.7 + f.p[1] * 71.3) % 6.283 + 6.283) % 6.283, tt = (performance.now() - this.t0) / 1000;
        const sw = Math.sin(tt * 0.55 + ph), alt = Math.sin(tt * 0.37 + ph * 1.7);
        const fast = f.type === 'ballistic' || f.type === 'cruise';
        const r = (f.hd || 0) * Math.PI / 180 + (fast ? 0.015 : 0.06) * sw, a = f.weak ? 0.6 : 1, c = f.col;
        const bank = Math.max(-1, Math.min(1, Math.cos(tt * 0.55 + ph) * 0.9));
        const sz = spr * (1 + 0.035 * alt), sh = spr * (0.22 + 0.06 * alt);
        const rc = [Math.min(1, c[0] * 1.15 + 0.15), Math.min(1, c[1] * 1.15 + 0.15), Math.min(1, c[2] * 1.15 + 0.15), a];
        const q = [[f._m[0], f._m[1], sz * 0.97, r, [1, 1, 1, a], 4, 0, 0, sh * 0.7, sh],
                   [f._m[0], f._m[1], sz, r, rc, 3 + (bank + 1) / 2 * 0.4]];
        this.draw(gl, this.quads(q), 2);
        if (f.type === 'jet') { // язик полум'я позаду сопла (сопло ≈ 0.88 напіврозміру від центру)
          const fs = sz * 0.85, back = sz * 0.86 + fs * 0.95, seed = ((f.p[0] * 97 + f.p[1] * 31) % 1 + 1) % 1;
          const nb = sz * 0.9, flick = 0.55 + 0.25 * Math.sin(tt * 29 + seed * 40) * Math.sin(tt * 13 + seed * 9);
          fl.push([f._m[0], f._m[1], sz * 0.55, r, [1, 0.45, 0.12, 0.55 * flick], 0, 0, 0, -Math.sin(r) * nb, Math.cos(r) * nb]); // відсвіт від сопла
          fl.push([f._m[0], f._m[1], fs, r, [1, 1, 1, seed], 6, 0, 0, -Math.sin(r) * back, Math.cos(r) * back]);
        }
      }
      if (fl.length) { gl.blendFunc(gl.ONE, gl.ONE); this.draw(gl, this.quads(fl), fl.length); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); }
      if (top.length) this.draw(gl, this.quads(top), top.length);
      map.triggerRepaint();
    },
  };
  window.FxLayer = FX;
})();
