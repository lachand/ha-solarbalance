/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const R = globalThis, Y = R.ShadowRoot && (R.ShadyCSS === void 0 || R.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, Q = Symbol(), ne = /* @__PURE__ */ new WeakMap();
let be = class {
  constructor(e, t, s) {
    if (this._$cssResult$ = !0, s !== Q) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = e, this.t = t;
  }
  get styleSheet() {
    let e = this.o;
    const t = this.t;
    if (Y && e === void 0) {
      const s = t !== void 0 && t.length === 1;
      s && (e = ne.get(t)), e === void 0 && ((this.o = e = new CSSStyleSheet()).replaceSync(this.cssText), s && ne.set(t, e));
    }
    return e;
  }
  toString() {
    return this.cssText;
  }
};
const De = (i) => new be(typeof i == "string" ? i : i + "", void 0, Q), Re = (i, ...e) => {
  const t = i.length === 1 ? i[0] : e.reduce((s, r, n) => s + ((a) => {
    if (a._$cssResult$ === !0) return a.cssText;
    if (typeof a == "number") return a;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + a + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(r) + i[n + 1], i[0]);
  return new be(t, i, Q);
}, Be = (i, e) => {
  if (Y) i.adoptedStyleSheets = e.map((t) => t instanceof CSSStyleSheet ? t : t.styleSheet);
  else for (const t of e) {
    const s = document.createElement("style"), r = R.litNonce;
    r !== void 0 && s.setAttribute("nonce", r), s.textContent = t.cssText, i.appendChild(s);
  }
}, ae = Y ? (i) => i : (i) => i instanceof CSSStyleSheet ? ((e) => {
  let t = "";
  for (const s of e.cssRules) t += s.cssText;
  return De(t);
})(i) : i;
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const { is: Ie, defineProperty: je, getOwnPropertyDescriptor: qe, getOwnPropertyNames: Fe, getOwnPropertySymbols: ze, getPrototypeOf: We } = Object, q = globalThis, oe = q.trustedTypes, Ve = oe ? oe.emptyScript : "", Ge = q.reactiveElementPolyfillSupport, P = (i, e) => i, B = { toAttribute(i, e) {
  switch (e) {
    case Boolean:
      i = i ? Ve : null;
      break;
    case Object:
    case Array:
      i = i == null ? i : JSON.stringify(i);
  }
  return i;
}, fromAttribute(i, e) {
  let t = i;
  switch (e) {
    case Boolean:
      t = i !== null;
      break;
    case Number:
      t = i === null ? null : Number(i);
      break;
    case Object:
    case Array:
      try {
        t = JSON.parse(i);
      } catch {
        t = null;
      }
  }
  return t;
} }, X = (i, e) => !Ie(i, e), le = { attribute: !0, type: String, converter: B, reflect: !1, useDefault: !1, hasChanged: X };
Symbol.metadata ??= Symbol("metadata"), q.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let S = class extends HTMLElement {
  static addInitializer(e) {
    this._$Ei(), (this.l ??= []).push(e);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(e, t = le) {
    if (t.state && (t.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(e) && ((t = Object.create(t)).wrapped = !0), this.elementProperties.set(e, t), !t.noAccessor) {
      const s = Symbol(), r = this.getPropertyDescriptor(e, s, t);
      r !== void 0 && je(this.prototype, e, r);
    }
  }
  static getPropertyDescriptor(e, t, s) {
    const { get: r, set: n } = qe(this.prototype, e) ?? { get() {
      return this[t];
    }, set(a) {
      this[t] = a;
    } };
    return { get: r, set(a) {
      const o = r?.call(this);
      n?.call(this, a), this.requestUpdate(e, o, s);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(e) {
    return this.elementProperties.get(e) ?? le;
  }
  static _$Ei() {
    if (this.hasOwnProperty(P("elementProperties"))) return;
    const e = We(this);
    e.finalize(), e.l !== void 0 && (this.l = [...e.l]), this.elementProperties = new Map(e.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(P("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(P("properties"))) {
      const t = this.properties, s = [...Fe(t), ...ze(t)];
      for (const r of s) this.createProperty(r, t[r]);
    }
    const e = this[Symbol.metadata];
    if (e !== null) {
      const t = litPropertyMetadata.get(e);
      if (t !== void 0) for (const [s, r] of t) this.elementProperties.set(s, r);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [t, s] of this.elementProperties) {
      const r = this._$Eu(t, s);
      r !== void 0 && this._$Eh.set(r, t);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(e) {
    const t = [];
    if (Array.isArray(e)) {
      const s = new Set(e.flat(1 / 0).reverse());
      for (const r of s) t.unshift(ae(r));
    } else e !== void 0 && t.push(ae(e));
    return t;
  }
  static _$Eu(e, t) {
    const s = t.attribute;
    return s === !1 ? void 0 : typeof s == "string" ? s : typeof e == "string" ? e.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((e) => this.enableUpdating = e), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((e) => e(this));
  }
  addController(e) {
    (this._$EO ??= /* @__PURE__ */ new Set()).add(e), this.renderRoot !== void 0 && this.isConnected && e.hostConnected?.();
  }
  removeController(e) {
    this._$EO?.delete(e);
  }
  _$E_() {
    const e = /* @__PURE__ */ new Map(), t = this.constructor.elementProperties;
    for (const s of t.keys()) this.hasOwnProperty(s) && (e.set(s, this[s]), delete this[s]);
    e.size > 0 && (this._$Ep = e);
  }
  createRenderRoot() {
    const e = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return Be(e, this.constructor.elementStyles), e;
  }
  connectedCallback() {
    this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(!0), this._$EO?.forEach((e) => e.hostConnected?.());
  }
  enableUpdating(e) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((e) => e.hostDisconnected?.());
  }
  attributeChangedCallback(e, t, s) {
    this._$AK(e, s);
  }
  _$ET(e, t) {
    const s = this.constructor.elementProperties.get(e), r = this.constructor._$Eu(e, s);
    if (r !== void 0 && s.reflect === !0) {
      const n = (s.converter?.toAttribute !== void 0 ? s.converter : B).toAttribute(t, s.type);
      this._$Em = e, n == null ? this.removeAttribute(r) : this.setAttribute(r, n), this._$Em = null;
    }
  }
  _$AK(e, t) {
    const s = this.constructor, r = s._$Eh.get(e);
    if (r !== void 0 && this._$Em !== r) {
      const n = s.getPropertyOptions(r), a = typeof n.converter == "function" ? { fromAttribute: n.converter } : n.converter?.fromAttribute !== void 0 ? n.converter : B;
      this._$Em = r;
      const o = a.fromAttribute(t, n.type);
      this[r] = o ?? this._$Ej?.get(r) ?? o, this._$Em = null;
    }
  }
  requestUpdate(e, t, s, r = !1, n) {
    if (e !== void 0) {
      const a = this.constructor;
      if (r === !1 && (n = this[e]), s ??= a.getPropertyOptions(e), !((s.hasChanged ?? X)(n, t) || s.useDefault && s.reflect && n === this._$Ej?.get(e) && !this.hasAttribute(a._$Eu(e, s)))) return;
      this.C(e, t, s);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(e, t, { useDefault: s, reflect: r, wrapped: n }, a) {
    s && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(e) && (this._$Ej.set(e, a ?? t ?? this[e]), n !== !0 || a !== void 0) || (this._$AL.has(e) || (this.hasUpdated || s || (t = void 0), this._$AL.set(e, t)), r === !0 && this._$Em !== e && (this._$Eq ??= /* @__PURE__ */ new Set()).add(e));
  }
  async _$EP() {
    this.isUpdatePending = !0;
    try {
      await this._$ES;
    } catch (t) {
      Promise.reject(t);
    }
    const e = this.scheduleUpdate();
    return e != null && await e, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
        for (const [r, n] of this._$Ep) this[r] = n;
        this._$Ep = void 0;
      }
      const s = this.constructor.elementProperties;
      if (s.size > 0) for (const [r, n] of s) {
        const { wrapped: a } = n, o = this[r];
        a !== !0 || this._$AL.has(r) || o === void 0 || this.C(r, void 0, n, o);
      }
    }
    let e = !1;
    const t = this._$AL;
    try {
      e = this.shouldUpdate(t), e ? (this.willUpdate(t), this._$EO?.forEach((s) => s.hostUpdate?.()), this.update(t)) : this._$EM();
    } catch (s) {
      throw e = !1, this._$EM(), s;
    }
    e && this._$AE(t);
  }
  willUpdate(e) {
  }
  _$AE(e) {
    this._$EO?.forEach((t) => t.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(e)), this.updated(e);
  }
  _$EM() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = !1;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$ES;
  }
  shouldUpdate(e) {
    return !0;
  }
  update(e) {
    this._$Eq &&= this._$Eq.forEach((t) => this._$ET(t, this[t])), this._$EM();
  }
  updated(e) {
  }
  firstUpdated(e) {
  }
};
S.elementStyles = [], S.shadowRootOptions = { mode: "open" }, S[P("elementProperties")] = /* @__PURE__ */ new Map(), S[P("finalized")] = /* @__PURE__ */ new Map(), Ge?.({ ReactiveElement: S }), (q.reactiveElementVersions ??= []).push("2.1.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const ee = globalThis, ce = (i) => i, I = ee.trustedTypes, he = I ? I.createPolicy("lit-html", { createHTML: (i) => i }) : void 0, Ae = "$lit$", f = `lit$${Math.random().toFixed(9).slice(2)}$`, Se = "?" + f, Ke = `<${Se}>`, y = document, N = () => y.createComment(""), T = (i) => i === null || typeof i != "object" && typeof i != "function", te = Array.isArray, Ze = (i) => te(i) || typeof i?.[Symbol.iterator] == "function", V = `[ 	
\f\r]`, E = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, de = /-->/g, ue = />/g, v = RegExp(`>|${V}(?:([^\\s"'>=/]+)(${V}*=${V}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), pe = /'/g, me = /"/g, we = /^(?:script|style|textarea|title)$/i, Je = (i) => (e, ...t) => ({ _$litType$: i, strings: e, values: t }), $e = Je(1), b = Symbol.for("lit-noChange"), u = Symbol.for("lit-nothing"), ge = /* @__PURE__ */ new WeakMap(), _ = y.createTreeWalker(y, 129);
function Ce(i, e) {
  if (!te(i) || !i.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return he !== void 0 ? he.createHTML(e) : e;
}
const Ye = (i, e) => {
  const t = i.length - 1, s = [];
  let r, n = e === 2 ? "<svg>" : e === 3 ? "<math>" : "", a = E;
  for (let o = 0; o < t; o++) {
    const l = i[o];
    let c, h, d = -1, p = 0;
    for (; p < l.length && (a.lastIndex = p, h = a.exec(l), h !== null); ) p = a.lastIndex, a === E ? h[1] === "!--" ? a = de : h[1] !== void 0 ? a = ue : h[2] !== void 0 ? (we.test(h[2]) && (r = RegExp("</" + h[2], "g")), a = v) : h[3] !== void 0 && (a = v) : a === v ? h[0] === ">" ? (a = r ?? E, d = -1) : h[1] === void 0 ? d = -2 : (d = a.lastIndex - h[2].length, c = h[1], a = h[3] === void 0 ? v : h[3] === '"' ? me : pe) : a === me || a === pe ? a = v : a === de || a === ue ? a = E : (a = v, r = void 0);
    const $ = a === v && i[o + 1].startsWith("/>") ? " " : "";
    n += a === E ? l + Ke : d >= 0 ? (s.push(c), l.slice(0, d) + Ae + l.slice(d) + f + $) : l + f + (d === -2 ? o : $);
  }
  return [Ce(i, n + (i[t] || "<?>") + (e === 2 ? "</svg>" : e === 3 ? "</math>" : "")), s];
};
class O {
  constructor({ strings: e, _$litType$: t }, s) {
    let r;
    this.parts = [];
    let n = 0, a = 0;
    const o = e.length - 1, l = this.parts, [c, h] = Ye(e, t);
    if (this.el = O.createElement(c, s), _.currentNode = this.el.content, t === 2 || t === 3) {
      const d = this.el.content.firstChild;
      d.replaceWith(...d.childNodes);
    }
    for (; (r = _.nextNode()) !== null && l.length < o; ) {
      if (r.nodeType === 1) {
        if (r.hasAttributes()) for (const d of r.getAttributeNames()) if (d.endsWith(Ae)) {
          const p = h[a++], $ = r.getAttribute(d).split(f), g = /([.?@])?(.*)/.exec(p);
          l.push({ type: 1, index: n, name: g[2], strings: $, ctor: g[1] === "." ? Xe : g[1] === "?" ? et : g[1] === "@" ? tt : F }), r.removeAttribute(d);
        } else d.startsWith(f) && (l.push({ type: 6, index: n }), r.removeAttribute(d));
        if (we.test(r.tagName)) {
          const d = r.textContent.split(f), p = d.length - 1;
          if (p > 0) {
            r.textContent = I ? I.emptyScript : "";
            for (let $ = 0; $ < p; $++) r.append(d[$], N()), _.nextNode(), l.push({ type: 2, index: ++n });
            r.append(d[p], N());
          }
        }
      } else if (r.nodeType === 8) if (r.data === Se) l.push({ type: 2, index: n });
      else {
        let d = -1;
        for (; (d = r.data.indexOf(f, d + 1)) !== -1; ) l.push({ type: 7, index: n }), d += f.length - 1;
      }
      n++;
    }
  }
  static createElement(e, t) {
    const s = y.createElement("template");
    return s.innerHTML = e, s;
  }
}
function C(i, e, t = i, s) {
  if (e === b) return e;
  let r = s !== void 0 ? t._$Co?.[s] : t._$Cl;
  const n = T(e) ? void 0 : e._$litDirective$;
  return r?.constructor !== n && (r?._$AO?.(!1), n === void 0 ? r = void 0 : (r = new n(i), r._$AT(i, t, s)), s !== void 0 ? (t._$Co ??= [])[s] = r : t._$Cl = r), r !== void 0 && (e = C(i, r._$AS(i, e.values), r, s)), e;
}
class Qe {
  constructor(e, t) {
    this._$AV = [], this._$AN = void 0, this._$AD = e, this._$AM = t;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(e) {
    const { el: { content: t }, parts: s } = this._$AD, r = (e?.creationScope ?? y).importNode(t, !0);
    _.currentNode = r;
    let n = _.nextNode(), a = 0, o = 0, l = s[0];
    for (; l !== void 0; ) {
      if (a === l.index) {
        let c;
        l.type === 2 ? c = new U(n, n.nextSibling, this, e) : l.type === 1 ? c = new l.ctor(n, l.name, l.strings, this, e) : l.type === 6 && (c = new st(n, this, e)), this._$AV.push(c), l = s[++o];
      }
      a !== l?.index && (n = _.nextNode(), a++);
    }
    return _.currentNode = y, r;
  }
  p(e) {
    let t = 0;
    for (const s of this._$AV) s !== void 0 && (s.strings !== void 0 ? (s._$AI(e, s, t), t += s.strings.length - 2) : s._$AI(e[t])), t++;
  }
}
class U {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(e, t, s, r) {
    this.type = 2, this._$AH = u, this._$AN = void 0, this._$AA = e, this._$AB = t, this._$AM = s, this.options = r, this._$Cv = r?.isConnected ?? !0;
  }
  get parentNode() {
    let e = this._$AA.parentNode;
    const t = this._$AM;
    return t !== void 0 && e?.nodeType === 11 && (e = t.parentNode), e;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(e, t = this) {
    e = C(this, e, t), T(e) ? e === u || e == null || e === "" ? (this._$AH !== u && this._$AR(), this._$AH = u) : e !== this._$AH && e !== b && this._(e) : e._$litType$ !== void 0 ? this.$(e) : e.nodeType !== void 0 ? this.T(e) : Ze(e) ? this.k(e) : this._(e);
  }
  O(e) {
    return this._$AA.parentNode.insertBefore(e, this._$AB);
  }
  T(e) {
    this._$AH !== e && (this._$AR(), this._$AH = this.O(e));
  }
  _(e) {
    this._$AH !== u && T(this._$AH) ? this._$AA.nextSibling.data = e : this.T(y.createTextNode(e)), this._$AH = e;
  }
  $(e) {
    const { values: t, _$litType$: s } = e, r = typeof s == "number" ? this._$AC(e) : (s.el === void 0 && (s.el = O.createElement(Ce(s.h, s.h[0]), this.options)), s);
    if (this._$AH?._$AD === r) this._$AH.p(t);
    else {
      const n = new Qe(r, this), a = n.u(this.options);
      n.p(t), this.T(a), this._$AH = n;
    }
  }
  _$AC(e) {
    let t = ge.get(e.strings);
    return t === void 0 && ge.set(e.strings, t = new O(e)), t;
  }
  k(e) {
    te(this._$AH) || (this._$AH = [], this._$AR());
    const t = this._$AH;
    let s, r = 0;
    for (const n of e) r === t.length ? t.push(s = new U(this.O(N()), this.O(N()), this, this.options)) : s = t[r], s._$AI(n), r++;
    r < t.length && (this._$AR(s && s._$AB.nextSibling, r), t.length = r);
  }
  _$AR(e = this._$AA.nextSibling, t) {
    for (this._$AP?.(!1, !0, t); e !== this._$AB; ) {
      const s = ce(e).nextSibling;
      ce(e).remove(), e = s;
    }
  }
  setConnected(e) {
    this._$AM === void 0 && (this._$Cv = e, this._$AP?.(e));
  }
}
let F = class {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(e, t, s, r, n) {
    this.type = 1, this._$AH = u, this._$AN = void 0, this.element = e, this.name = t, this._$AM = r, this.options = n, s.length > 2 || s[0] !== "" || s[1] !== "" ? (this._$AH = Array(s.length - 1).fill(new String()), this.strings = s) : this._$AH = u;
  }
  _$AI(e, t = this, s, r) {
    const n = this.strings;
    let a = !1;
    if (n === void 0) e = C(this, e, t, 0), a = !T(e) || e !== this._$AH && e !== b, a && (this._$AH = e);
    else {
      const o = e;
      let l, c;
      for (e = n[0], l = 0; l < n.length - 1; l++) c = C(this, o[s + l], t, l), c === b && (c = this._$AH[l]), a ||= !T(c) || c !== this._$AH[l], c === u ? e = u : e !== u && (e += (c ?? "") + n[l + 1]), this._$AH[l] = c;
    }
    a && !r && this.j(e);
  }
  j(e) {
    e === u ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, e ?? "");
  }
};
class Xe extends F {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(e) {
    this.element[this.name] = e === u ? void 0 : e;
  }
}
class et extends F {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(e) {
    this.element.toggleAttribute(this.name, !!e && e !== u);
  }
}
class tt extends F {
  constructor(e, t, s, r, n) {
    super(e, t, s, r, n), this.type = 5;
  }
  _$AI(e, t = this) {
    if ((e = C(this, e, t, 0) ?? u) === b) return;
    const s = this._$AH, r = e === u && s !== u || e.capture !== s.capture || e.once !== s.once || e.passive !== s.passive, n = e !== u && (s === u || r);
    r && this.element.removeEventListener(this.name, this, s), n && this.element.addEventListener(this.name, this, e), this._$AH = e;
  }
  handleEvent(e) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, e) : this._$AH.handleEvent(e);
  }
}
class st {
  constructor(e, t, s) {
    this.element = e, this.type = 6, this._$AN = void 0, this._$AM = t, this.options = s;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(e) {
    C(this, e);
  }
}
const it = ee.litHtmlPolyfillSupport;
it?.(O, U), (ee.litHtmlVersions ??= []).push("3.3.2");
const rt = (i, e, t) => {
  const s = t?.renderBefore ?? e;
  let r = s._$litPart$;
  if (r === void 0) {
    const n = t?.renderBefore ?? null;
    s._$litPart$ = r = new U(e.insertBefore(N(), n), n, void 0, t ?? {});
  }
  return r._$AI(i), r;
};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const se = globalThis;
let k = class extends S {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const e = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= e.firstChild, e;
  }
  update(e) {
    const t = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(e), this._$Do = rt(t, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return b;
  }
};
k._$litElement$ = !0, k.finalized = !0, se.litElementHydrateSupport?.({ LitElement: k });
const nt = se.litElementPolyfillSupport;
nt?.({ LitElement: k });
(se.litElementVersions ??= []).push("4.2.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const at = { attribute: !0, type: String, converter: B, reflect: !1, hasChanged: X }, ot = (i = at, e, t) => {
  const { kind: s, metadata: r } = t;
  let n = globalThis.litPropertyMetadata.get(r);
  if (n === void 0 && globalThis.litPropertyMetadata.set(r, n = /* @__PURE__ */ new Map()), s === "setter" && ((i = Object.create(i)).wrapped = !0), n.set(t.name, i), s === "accessor") {
    const { name: a } = t;
    return { set(o) {
      const l = e.get.call(this);
      e.set.call(this, o), this.requestUpdate(a, l, i, !0, o);
    }, init(o) {
      return o !== void 0 && this.C(a, void 0, i, o), o;
    } };
  }
  if (s === "setter") {
    const { name: a } = t;
    return function(o) {
      const l = this[a];
      e.call(this, o), this.requestUpdate(a, l, i, !0, o);
    };
  }
  throw Error("Unsupported decorator location: " + s);
};
function Me(i) {
  return (e, t) => typeof t == "object" ? ot(i, e, t) : ((s, r, n) => {
    const a = r.hasOwnProperty(n);
    return r.constructor.createProperty(n, s), a ? Object.getOwnPropertyDescriptor(r, n) : void 0;
  })(i, e, t);
}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
function Ee(i) {
  return Me({ ...i, state: !0, attribute: !1 });
}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const lt = { CHILD: 2 }, ct = (i) => (...e) => ({ _$litDirective$: i, values: e });
class ht {
  constructor(e) {
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AT(e, t, s) {
    this._$Ct = e, this._$AM = t, this._$Ci = s;
  }
  _$AS(e, t) {
    return this.update(e, t);
  }
  update(e, t) {
    return this.render(...t);
  }
}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
class Z extends ht {
  constructor(e) {
    if (super(e), this.it = u, e.type !== lt.CHILD) throw Error(this.constructor.directiveName + "() can only be used in child bindings");
  }
  render(e) {
    if (e === u || e == null) return this._t = void 0, this.it = e;
    if (e === b) return e;
    if (typeof e != "string") throw Error(this.constructor.directiveName + "() called with a non-string value");
    if (e === this.it) return this._t;
    this.it = e;
    const t = [e];
    return t.raw = t, this._t = { _$litType$: this.constructor.resultType, strings: t, values: [] };
  }
}
Z.directiveName = "unsafeHTML", Z.resultType = 1;
const dt = ct(Z), ut = {
  // Tabs and header
  Maintenant: "Now",
  Pilotage: "Control",
  Batteries: "Batteries",
  Santé: "Health",
  Stratégie: "Strategy",
  "Contraste élevé": "High contrast",
  "Mesures en direct": "Live measures",
  "À jour": "Up to date",
  "Données anciennes": "Stale data",
  Normal: "Normal",
  Tempête: "Storm",
  Dégradé: "Degraded",
  "En pause": "Paused",
  Manuel: "Manual",
  Attention: "Warning",
  Critique: "Critical",
  Information: "Information",
  Solaire: "Solar",
  Réseau: "Grid",
  Maison: "Home",
  "Niveau moyen": "Average level",
  Soutirage: "Import",
  Injection: "Export",
  Équilibre: "Balanced",
  Production: "Production",
  "Au repos": "Idle",
  Consommation: "Consumption",
  Charge: "Charging",
  Décharge: "Discharging",
  charge: "charging",
  décharge: "discharging",
  repos: "idle",
  solaire: "solar",
  réseau: "grid",
  batteries: "batteries",
  maison: "home",
  maintenant: "now",
  "aujourd'hui": "today",
  // Now
  "Flux en temps réel": "Real-time flow",
  "Flux d'énergie": "Energy flow",
  "Bilan du jour": "Today's summary",
  Énergie: "Energy",
  Argent: "Money",
  Autoconsommation: "Self-consumption",
  Autonomie: "Autonomy",
  Soutiré: "Imported",
  Injecté: "Exported",
  "Solaire restant": "Solar remaining",
  "Coût du réseau": "Grid cost",
  "Économies du jour": "Savings today",
  "Économies du mois": "Savings this month",
  "Économies de l'année": "Savings this year",
  "Aucun capteur configuré.": "No sensor configured.",
  "Ce que fait le système": "What the system is doing",
  Puissance: "Power",
  "Période du graphique": "Chart period",
  Jour: "Day",
  "Prévision solaire": "Solar forecast",
  "Chargement de l'historique": "Loading history",
  "Aucune donnée sur la période.": "No data for this period.",
  "Pic capteur masqué": "Hidden sensor spike",
  "Pics isolés d'un capteur, masqués pour la lisibilité. La régulation les filtre déjà.": "Isolated sensor spikes, hidden for readability. The regulation already filters them.",
  "pic(s) masqué(s)": "spike(s) hidden",
  "Masquer les pics": "Hide spikes",
  "Afficher les pics bruts": "Show raw spikes",
  "Mode dégradé : une ou plusieurs entités sont indisponibles.": "Degraded mode: one or more entities are unavailable.",
  "Mode tempête actif : préparation du stockage en cours.": "Storm mode active: preparing storage.",
  "Vigilance météo en cours.": "Weather warning in effect.",
  "Délestage prioritaire de la batterie : gros consommateurs coupés": "Battery-priority shedding: large loads switched off",
  déficit: "deficit",
  "Charge rapide du véhicule assistée par les batteries (solaire récupérable).": "Fast vehicle charging assisted by the batteries (recoverable solar).",
  Échéance: "Deadline",
  "charge réseau forcée": "grid charging forced",
  restants: "remaining",
  "point d'attention": "item needs attention",
  "points d'attention": "items need attention",
  "Ouvrir la santé": "Open health",
  // Control
  Régulation: "Regulation",
  "Garde-fou actif": "Active limit",
  "Réseau filtré": "Filtered grid",
  "Cible du parc": "Fleet target",
  "Correction zéro-injection": "Zero-injection correction",
  "Offre de l'équaliseur": "Equaliser offer",
  "Limite de sortie solaire": "Solar output limit",
  Cible: "Target",
  "Parc réel": "Actual fleet",
  "Cible et parc réel, dernières minutes": "Target and actual fleet, last minutes",
  "Contrôles rapides": "Quick controls",
  "Mettre en pause": "Pause",
  Reprendre: "Resume",
  "Charger à 100 %": "Charge to 100%",
  "Décharger à 20 %": "Discharge to 20%",
  "Mode tempête": "Storm mode",
  "Forcer la charge à 100 % ?": "Force charge to 100%?",
  "Forcer la décharge à 20 % ?": "Force discharge to 20%?",
  "Activer le mode tempête ?": "Activate storm mode?",
  Annuler: "Cancel",
  Confirmer: "Confirm",
  Valider: "Confirm",
  Consommateurs: "Loads",
  "Charger maintenant": "Charge now",
  "Heures creuses seulement": "Off-peak only",
  "Solaire seulement": "Solar only",
  "Ne pas délester": "Keep running",
  "Puissance souscrite": "Subscribed power",
  "Soutirage instantané": "Instant import",
  "Soutirage instantané par rapport à la puissance souscrite": "Instant import against the subscribed power",
  Élevé: "High",
  "Limite proche": "Near limit",
  "Plan indicatif sur 24 h": "Advisory plan, 24 h",
  "Plan indicatif de la batterie sur 24 h": "Advisory battery plan, 24 h",
  "barres pleines, charge prévue ; barres creuses, décharge prévue ; ligne, niveau de charge prévu.": "filled bars, planned charge; outlined bars, planned discharge; line, planned level.",
  "Charge prévue": "Planned charge",
  "Décharge prévue": "Planned discharge",
  "Niveau prévu": "Planned level",
  de: "from",
  à: "to",
  "Aucune action batterie planifiée": "No battery action planned",
  Heure: "Time",
  Batterie: "Battery",
  Niveau: "Level",
  Coût: "Cost",
  "Indicatif : ce plan n'est pas appliqué aux équipements.": "Advisory only: this plan is not applied to any equipment.",
  "Bridage solaire": "Solar curtailment",
  bridé: "capped",
  "Solaire caché estimé": "Estimated hidden solar",
  // Batteries
  "Parc de batteries": "Battery fleet",
  "Énergie restante": "Energy remaining",
  "Énergie exploitable": "Usable energy",
  "Avant d'être pleines": "Until full",
  "Avant d'être vides": "Until empty",
  "Niveau de charge": "State of charge",
  "Niveau de charge par batterie": "State of charge per battery",
  Plancher: "Floor",
  "Hors ligne": "Offline",
  "SoC figé": "SoC frozen",
  "puissance figée": "power frozen",
  "hors ligne": "offline",
  cloud: "cloud",
  "Puissance de la batterie": "Battery power",
  "Consigne de charge": "Charge setpoint",
  "Consigne de décharge": "Discharge setpoint",
  "Production solaire": "Solar production",
  "Limite de production": "Output limit",
  "Température de la batterie": "Battery temperature",
  "Température du régulateur solaire": "Solar charger temperature",
  "Aucun appareil batterie détecté.": "No battery device detected.",
  // Health
  "Santé de l'installation": "Installation health",
  Bonne: "Good",
  Moyenne: "Fair",
  Dégradée: "Degraded",
  "Score de santé de l'installation": "Installation health score",
  "Alertes en cours": "Active alerts",
  "Aucune alerte en cours.": "No active alert.",
  "Appareil en double": "Duplicate device",
  "Écriture non appliquée": "Write not applied",
  "Mode dégradé : entités indisponibles": "Degraded mode: entities unavailable",
  "Batterie cloud en décharge (délai dépassé) : consommation de base plafonnée": "Cloud battery discharging (timeout): baseline capped",
  "Consommation de base négative": "Negative baseline consumption",
  "vérifier la correspondance des capteurs": "check the sensor mapping",
  "Frise d'anomalies": "Anomaly timeline",
  "Liaisons (24 h)": "Links (24 h)",
  "Liaisons peu fiables (24 h)": "Unreliable links (24 h)",
  "Toutes les liaisons sont stables.": "All links are stable.",
  "Peu fiable": "Unreliable",
  Instable: "Flaky",
  disponibilité: "availability",
  "plus long trou": "longest gap",
  coupures: "dropouts",
  "Apport de l'orchestration": "What the orchestration adds",
  "Gain par rapport à l'autoconsommation simple": "Gain over plain self-consumption",
  "Facture réelle": "Actual bill",
  "Facture sans pilotage": "Bill without orchestration",
  "Charge conservée": "Charge held back",
  "Comparaison en cours : trop tôt pour donner un chiffre.": "Comparison under way: too early for a figure.",
  "Même matériel, même maison, laissés en autoconsommation simple.": "Same hardware, same house, left to plain self-consumption.",
  "Consommation de veille": "Standby consumption",
  "Talon de nuit": "Night standby",
  "Recalculer le talon": "Recompute the standby baseline",
  "Après une charge de véhicule de nuit qui l'aurait faussé, le talon peut être recalculé à la prochaine nuit calme.": "After a night vehicle charge that skewed it, the baseline can be recomputed at the next quiet night.",
  "Diagnostic de la régulation": "Regulation diagnostics",
  "Par batterie": "Per battery",
  "Consignes écrites": "Written setpoints"
}, xe = " ", pt = "−", fe = /* @__PURE__ */ new Map();
function mt(i, e) {
  const t = `${i}|${e}`;
  let s = fe.get(t);
  return s || (s = new Intl.NumberFormat(i, {
    minimumFractionDigits: e,
    maximumFractionDigits: e
  }), fe.set(t, s)), s;
}
function j(i, e = 0, t = "fr") {
  if (i == null || !Number.isFinite(i)) return "—";
  const s = mt(t, e).format(i);
  return (Number(i.toFixed(e)) === 0 ? s.replace("-", "") : s).replace("-", pt);
}
function Pe(i, e) {
  return e ? `${i}${xe}${e}` : i;
}
function ke(i, e = "fr") {
  return i == null || !Number.isFinite(i) ? { value: "—", unit: "W" } : Math.abs(i) >= 1e3 ? { value: j(i / 1e3, 2, e), unit: "kW" } : { value: j(Math.round(i), 0, e), unit: "W" };
}
function x(i, e = "fr") {
  const t = ke(i, e);
  return t.value === "—" ? "—" : Pe(t.value, t.unit);
}
function m(i) {
  return String(i ?? "").replace(
    /[&<>"']/g,
    (e) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[e]
  );
}
const $t = {
  normal: ["ok", "Normal"],
  storm: ["attention", "Tempête"],
  degraded: ["critique", "Dégradé"],
  paused: ["inactif", "En pause"],
  manual_override: ["attention", "Manuel"]
};
function gt(i) {
  return $t[i] || ["inactif", i || "—"];
}
const ft = {
  ok: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
  attention: '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  critique: '<path d="M8.5 3h7L21 8.5v7L15.5 21h-7L3 15.5v-7z"/><path d="M12 8v5M12 16v.1"/>',
  inactif: '<circle cx="12" cy="12" r="9" stroke-dasharray="3 3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.1"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>',
  grid: '<path d="M12 2.5l-5 19M12 2.5l5 19M8.2 13h7.6M9.6 8h4.8M6.5 21.5h11"/>',
  battery: '<rect x="3" y="7" width="16" height="10" rx="1"/><path d="M21 10.5v3M7 10.5v3M11 10.5v3"/>',
  home: '<path d="M3.5 11.5L12 4l8.5 7.5M6 10v10h12V10"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  play: '<path d="M7 5l11 7-11 7z"/>',
  bolt: '<path d="M13 2.5L5 13.5h6l-1 8 8-11h-6z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  edit: '<path d="M4 20l1-4L16 5l3 3L8 19z"/>',
  refresh: '<path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/>',
  storm: '<path d="M7 16a4.5 4.5 0 01-.5-9A6 6 0 0118 8.5 3.8 3.8 0 0117.5 16"/><path d="M12.5 12l-2.5 4h3l-1.5 4"/>',
  plug: '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 01-12 0zM12 17v4"/>'
};
function Ne(i, e = 16) {
  return `<svg class="ic" viewBox="0 0 24 24" width="${e}" height="${e}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ft[i] || ""}</svg>`;
}
const vt = {
  ok: "ok",
  attention: "attention",
  critique: "critique",
  inactif: "inactif",
  info: "info"
};
function _t(i, e, t = "") {
  const s = t ? ` title="${m(t)}"` : "";
  return `<span class="sg-stamp st-${i}" role="status"${s}>${Ne(vt[i], 14)}<span>${m(e)}</span></span>`;
}
function ve(i, e = "", t = "") {
  const s = e ? `<span class="mu">${m(e)}</span>` : "";
  return `<span class="mesure ${t}"><span class="mv">${i}</span>${s}</span>`;
}
function _e(i, e = "") {
  const t = String(i), s = t.indexOf(" ");
  return s < 0 ? ve(m(t), "", e) : ve(m(t.slice(0, s)), t.slice(s + 1), e);
}
function yt(i, e, t = "") {
  const s = t ? `<div class="tn">${m(t)}</div>` : "";
  return `<div class="tile"><div class="tl">${m(i)}</div>${e}${s}</div>`;
}
function bt(i, e, { tick: t = null, tone: s = "" } = {}) {
  const r = i == null ? 0 : Math.max(0, Math.min(100, i)), n = t != null ? `<span class="bar-tick" style="left:${t}%"></span>` : "", a = i == null ? "" : ` aria-valuenow="${Math.round(r)}"`;
  return `<div class="bar ${s}" role="meter" aria-valuemin="0" aria-valuemax="100"${a} aria-label="${m(e)}"><span class="bar-fill" style="width:${r}%"></span>${n}</div>`;
}
const At = 480, St = 178, ye = 124, G = 66, w = 20, H = {
  pv: { color: "var(--production)", dash: "", marker: "ah-pv" },
  grid: { color: "var(--consommation)", dash: "8 5", marker: "ah-grid" },
  batt: { color: "var(--stockage)", dash: "1.5 5", marker: "ah-batt", round: !0 }
};
function K(i, e, t) {
  const s = Math.abs(e || 0);
  if (s < w) return `<path d="${i}" class="flow-off"/>`;
  const r = Math.max(2, Math.min(7, 2 + s / 400)).toFixed(1), n = Math.max(0.6, 2 - s / 1e3).toFixed(2), a = t.dash ? ` stroke-dasharray="${t.dash}"` : "", o = t.round ? ' stroke-linecap="round"' : "", l = e > 0, c = l ? `marker-end="url(#${t.marker})"` : `marker-start="url(#${t.marker})"`, h = t.dash ? ` class="flow-anim ${l ? "in" : "out"}" style="animation-duration:${n}s"` : "";
  return `<path d="${i}" fill="none" stroke="${t.color}" stroke-width="${r}"${a}${o} ${c}${h}/>`;
}
function L(i, e, t, s, r, n, a, o) {
  const l = i - ye / 2, c = e - G / 2, h = ke(r, o);
  return `
    <g class="flow-node">
      <rect x="${l}" y="${c}" width="${ye}" height="${G}" rx="2" class="fn-box"/>
      <rect x="${l}" y="${c}" width="3" height="${G}" fill="${a}"/>
      <g transform="translate(${l + 10} ${c + 10})" style="color:${a}">${Ne(t, 20)}</g>
      <text x="${l + 38}" y="${c + 20}" class="fn-lbl">${m(s)}</text>
      <text x="${l + 38}" y="${c + 42}"><tspan class="fn-val">${m(h.value)}</tspan><tspan class="fn-unit" dx="3">${h.unit}</tspan></text>
      <text x="${l + 38}" y="${c + 59}" class="fn-sub">${m(n)}</text>
    </g>`;
}
function wt(i) {
  const { pv: e, grid: t, batt: s, home: r, soc: n, lang: a, t: o } = i, l = t > w ? "Soutirage" : t < -w ? "Injection" : "Équilibre", c = s > w ? "charge" : s < -w ? "décharge" : "repos", h = n != null ? `${j(Math.round(n), 0, a)}${xe}% · ${o(c)}` : o(c), d = e >= w ? "Production" : "Au repos", p = 141, $ = K("M240 68 L240 108", e, H.pv) + K(`M126 ${p} L178 ${p}`, t, H.grid) + K(`M354 ${p} L302 ${p}`, -s, H.batt), g = Object.values(H).map(
    (A) => `<marker id="${A.marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${A.color}"/></marker>`
  ).join(""), W = `${o("Flux d'énergie")} : ${o("solaire")} ${x(e, a)}, ${o("réseau")} ${x(t, a)} (${o(l).toLowerCase()}), ${o("batteries")} ${x(s, a)} (${o(c)}), ${o("maison")} ${x(r, a)}`;
  return `
    <svg viewBox="0 0 ${At} ${St}" class="flow" role="img" aria-label="${m(W)}">
      <defs>${g}</defs>
      ${$}
      ${L(240, 35, "sun", o("Solaire"), e, o(d), "var(--production)", a)}
      ${L(64, p, "grid", o("Réseau"), t, o(l), "var(--consommation)", a)}
      ${L(416, p, "battery", o("Batteries"), s, h, "var(--stockage)", a)}
      ${L(240, p, "home", o("Maison"), r, o("Consommation"), "var(--ink)", a)}
    </svg>`;
}
var Ct = Object.defineProperty, ie = (i, e, t, s) => {
  for (var r = void 0, n = i.length - 1, a; n >= 0; n--)
    (a = i[n]) && (r = a(e, t, r) || r);
  return r && Ct(e, t, r), r;
};
const Mt = {
  mode_entity: ["mode", "sensor.solarbalance_mode"],
  strategy_entity: ["dominant_strategy", "sensor.solarbalance_dominant_strategy"],
  grid_power_entity: ["grid_power", "sensor.solarbalance_grid_power"],
  pv_power_entity: ["pv_power", "sensor.solarbalance_pv_power"],
  battery_power_entity: ["battery_power", "sensor.solarbalance_battery_power"],
  battery_soc_entity: ["battery_soc_avg", "sensor.solarbalance_battery_soc_avg"]
}, J = new URL(
  /* @vite-ignore */
  "vendor/signature/",
  import.meta.url
).href, Et = new URL(
  /* @vite-ignore */
  "panel/panel.css",
  import.meta.url
).href, xt = {
  normal: "Normal",
  storm: "Tempête",
  vacation: "Vacances",
  self_consumption: "Autoconsommation",
  cost_min: "Coût minimal",
  revenue_max: "Revenu maximal",
  peak_shaving: "Écrêtage",
  backup: "Secours",
  longevity: "Longévité",
  manual_override: "Manuel",
  degraded: "Dégradé",
  paused: "En pause"
};
function D(i) {
  if (!i || i.state === "unavailable" || i.state === "unknown") return null;
  const e = parseFloat(i.state);
  return Number.isNaN(e) ? null : e;
}
function Pt() {
  if (document.getElementById("sb-signature-fonts")) return;
  const i = document.createElement("link");
  i.id = "sb-signature-fonts", i.rel = "stylesheet", i.href = `${J}fonts.css`, document.head.appendChild(i);
}
class z extends k {
  constructor() {
    super(...arguments), this._ready = !1;
  }
  static {
    this.styles = Re`
    :host {
      display: block;
      background: none;
      min-height: 0;
    }
    .sbc-root {
      visibility: hidden;
      color: var(--ink);
      font-family: var(--font-ui);
    }
    .sbc-root.ready {
      visibility: visible;
    }
    .sbc-foot {
      margin-top: var(--space-3);
    }
  `;
  }
  connectedCallback() {
    super.connectedCallback(), Pt(), window.setTimeout(() => this._ready = !0, 1500);
  }
  setConfig(e) {
    this._config = e;
  }
  getCardSize() {
    return 5;
  }
  /** Resolve an entity: explicit config, then translation_key (localised ids), then default id. */
  _entity(e) {
    const t = this.hass;
    if (!t) return;
    const s = this._config?.[e];
    if (s) return t.states[s];
    const [r, n] = Mt[e];
    for (const [a, o] of Object.entries(t.entities ?? {}))
      if (o.platform === "solarbalance" && o.translation_key === r) return t.states[a];
    return t.states[n];
  }
  render() {
    if (!this._config || !this.hass) return $e``;
    const e = this.hass, t = e.locale?.language || e.language || "fr", s = t.startsWith("en"), r = (M) => s ? ut[M] ?? M : M, n = this._entity("mode_entity"), a = this._entity("strategy_entity")?.state ?? "", o = D(this._entity("grid_power_entity")), l = D(this._entity("pv_power_entity")), c = D(this._entity("battery_power_entity")), h = D(this._entity("battery_soc_entity")), d = Math.max(0, (l ?? 0) + (o ?? 0) - (c ?? 0)), [p, $] = gt(n?.state), g = this._config.contrast ? "contrast" : e.themes?.darkMode ? "dark" : "light", W = this._config.title ?? "SolarBalance", A = (M, re, Le = "") => re == null ? "" : yt(r(M), _e(x(re, t)), Le), Te = o == null ? "" : o > 20 ? r("Soutirage") : o < -20 ? r("Injection") : "", Oe = c == null ? "" : c > 20 ? r("Charge") : c < -20 ? r("Décharge") : "", Ue = h == null ? "" : `<div class="tile"><div class="tl">${m(r("Niveau moyen"))}</div>${_e(
      Pe(j(Math.round(h), 0, t), "%")
    )}</div>`, He = `
      <div class="card-h"><h3 class="cote-rule">${m(W)}</h3>${_t(p, r($))}</div>
      ${wt({ pv: l ?? 0, grid: o ?? 0, batt: c ?? 0, home: d, soc: h, lang: t, t: r })}
      <div class="tiles sbc-foot">
        ${A("Solaire", l)}${A("Réseau", o, Te)}${A("Batteries", c, Oe)}${Ue}
      </div>
      ${h == null ? "" : `<div class="sbc-foot">${bt(h, r("Niveau de charge"))}</div>`}
      ${a ? `<p class="note">${m(r("Stratégie"))} : ${m(xt[a] ?? a)}</p>` : ""}`;
    return $e`
      <link rel="stylesheet" href="${J}tokens.scoped.css" />
      <link rel="stylesheet" href="${J}overlay.css" />
      <link
        rel="stylesheet"
        href="${Et}"
        @load=${() => this._ready = !0}
      />
      <div class="sg-scope sbc-root ${this._ready ? "ready" : ""}" data-theme="${g}">
        <section class="card">${dt(He)}</section>
      </div>
    `;
  }
}
ie([
  Me({ attribute: !1 })
], z.prototype, "hass");
ie([
  Ee()
], z.prototype, "_config");
ie([
  Ee()
], z.prototype, "_ready");
customElements.get("solarbalance-card") || (customElements.define("solarbalance-card", z), window.customCards = window.customCards ?? [], window.customCards.push({
  type: "solarbalance-card",
  name: "SolarBalance",
  description: "Flux d'énergie en temps réel (solaire, batteries, réseau, maison) et état du pilotage.",
  preview: !0
}));
export {
  z as SolarBalanceCard
};
