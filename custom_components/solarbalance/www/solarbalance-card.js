/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const R = globalThis, W = R.ShadowRoot && (R.ShadyCSS === void 0 || R.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, q = Symbol(), X = /* @__PURE__ */ new WeakMap();
let dt = class {
  constructor(t, e, s) {
    if (this._$cssResult$ = !0, s !== q) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (W && t === void 0) {
      const s = e !== void 0 && e.length === 1;
      s && (t = X.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), s && X.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const gt = (r) => new dt(typeof r == "string" ? r : r + "", void 0, q), yt = (r, ...t) => {
  const e = r.length === 1 ? r[0] : t.reduce((s, i, o) => s + ((n) => {
    if (n._$cssResult$ === !0) return n.cssText;
    if (typeof n == "number") return n;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + n + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(i) + r[o + 1], r[0]);
  return new dt(e, r, q);
}, bt = (r, t) => {
  if (W) r.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const s = document.createElement("style"), i = R.litNonce;
    i !== void 0 && s.setAttribute("nonce", i), s.textContent = e.cssText, r.appendChild(s);
  }
}, tt = W ? (r) => r : (r) => r instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const s of t.cssRules) e += s.cssText;
  return gt(e);
})(r) : r;
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const { is: At, defineProperty: xt, getOwnPropertyDescriptor: Et, getOwnPropertyNames: wt, getOwnPropertySymbols: St, getPrototypeOf: Ct } = Object, j = globalThis, et = j.trustedTypes, Mt = et ? et.emptyScript : "", Pt = j.reactiveElementPolyfillSupport, C = (r, t) => r, D = { toAttribute(r, t) {
  switch (t) {
    case Boolean:
      r = r ? Mt : null;
      break;
    case Object:
    case Array:
      r = r == null ? r : JSON.stringify(r);
  }
  return r;
}, fromAttribute(r, t) {
  let e = r;
  switch (t) {
    case Boolean:
      e = r !== null;
      break;
    case Number:
      e = r === null ? null : Number(r);
      break;
    case Object:
    case Array:
      try {
        e = JSON.parse(r);
      } catch {
        e = null;
      }
  }
  return e;
} }, F = (r, t) => !At(r, t), st = { attribute: !0, type: String, converter: D, reflect: !1, useDefault: !1, hasChanged: F };
Symbol.metadata ??= Symbol("metadata"), j.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let A = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ??= []).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = st) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const s = Symbol(), i = this.getPropertyDescriptor(t, s, e);
      i !== void 0 && xt(this.prototype, t, i);
    }
  }
  static getPropertyDescriptor(t, e, s) {
    const { get: i, set: o } = Et(this.prototype, t) ?? { get() {
      return this[e];
    }, set(n) {
      this[e] = n;
    } };
    return { get: i, set(n) {
      const l = i?.call(this);
      o?.call(this, n), this.requestUpdate(t, l, s);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? st;
  }
  static _$Ei() {
    if (this.hasOwnProperty(C("elementProperties"))) return;
    const t = Ct(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(C("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(C("properties"))) {
      const e = this.properties, s = [...wt(e), ...St(e)];
      for (const i of s) this.createProperty(i, e[i]);
    }
    const t = this[Symbol.metadata];
    if (t !== null) {
      const e = litPropertyMetadata.get(t);
      if (e !== void 0) for (const [s, i] of e) this.elementProperties.set(s, i);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [e, s] of this.elementProperties) {
      const i = this._$Eu(e, s);
      i !== void 0 && this._$Eh.set(i, e);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(t) {
    const e = [];
    if (Array.isArray(t)) {
      const s = new Set(t.flat(1 / 0).reverse());
      for (const i of s) e.unshift(tt(i));
    } else t !== void 0 && e.push(tt(t));
    return e;
  }
  static _$Eu(t, e) {
    const s = e.attribute;
    return s === !1 ? void 0 : typeof s == "string" ? s : typeof t == "string" ? t.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((t) => this.enableUpdating = t), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((t) => t(this));
  }
  addController(t) {
    (this._$EO ??= /* @__PURE__ */ new Set()).add(t), this.renderRoot !== void 0 && this.isConnected && t.hostConnected?.();
  }
  removeController(t) {
    this._$EO?.delete(t);
  }
  _$E_() {
    const t = /* @__PURE__ */ new Map(), e = this.constructor.elementProperties;
    for (const s of e.keys()) this.hasOwnProperty(s) && (t.set(s, this[s]), delete this[s]);
    t.size > 0 && (this._$Ep = t);
  }
  createRenderRoot() {
    const t = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return bt(t, this.constructor.elementStyles), t;
  }
  connectedCallback() {
    this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(!0), this._$EO?.forEach((t) => t.hostConnected?.());
  }
  enableUpdating(t) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((t) => t.hostDisconnected?.());
  }
  attributeChangedCallback(t, e, s) {
    this._$AK(t, s);
  }
  _$ET(t, e) {
    const s = this.constructor.elementProperties.get(t), i = this.constructor._$Eu(t, s);
    if (i !== void 0 && s.reflect === !0) {
      const o = (s.converter?.toAttribute !== void 0 ? s.converter : D).toAttribute(e, s.type);
      this._$Em = t, o == null ? this.removeAttribute(i) : this.setAttribute(i, o), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const s = this.constructor, i = s._$Eh.get(t);
    if (i !== void 0 && this._$Em !== i) {
      const o = s.getPropertyOptions(i), n = typeof o.converter == "function" ? { fromAttribute: o.converter } : o.converter?.fromAttribute !== void 0 ? o.converter : D;
      this._$Em = i;
      const l = n.fromAttribute(e, o.type);
      this[i] = l ?? this._$Ej?.get(i) ?? l, this._$Em = null;
    }
  }
  requestUpdate(t, e, s, i = !1, o) {
    if (t !== void 0) {
      const n = this.constructor;
      if (i === !1 && (o = this[t]), s ??= n.getPropertyOptions(t), !((s.hasChanged ?? F)(o, e) || s.useDefault && s.reflect && o === this._$Ej?.get(t) && !this.hasAttribute(n._$Eu(t, s)))) return;
      this.C(t, e, s);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: s, reflect: i, wrapped: o }, n) {
    s && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(t) && (this._$Ej.set(t, n ?? e ?? this[t]), o !== !0 || n !== void 0) || (this._$AL.has(t) || (this.hasUpdated || s || (e = void 0), this._$AL.set(t, e)), i === !0 && this._$Em !== t && (this._$Eq ??= /* @__PURE__ */ new Set()).add(t));
  }
  async _$EP() {
    this.isUpdatePending = !0;
    try {
      await this._$ES;
    } catch (e) {
      Promise.reject(e);
    }
    const t = this.scheduleUpdate();
    return t != null && await t, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
        for (const [i, o] of this._$Ep) this[i] = o;
        this._$Ep = void 0;
      }
      const s = this.constructor.elementProperties;
      if (s.size > 0) for (const [i, o] of s) {
        const { wrapped: n } = o, l = this[i];
        n !== !0 || this._$AL.has(i) || l === void 0 || this.C(i, void 0, o, l);
      }
    }
    let t = !1;
    const e = this._$AL;
    try {
      t = this.shouldUpdate(e), t ? (this.willUpdate(e), this._$EO?.forEach((s) => s.hostUpdate?.()), this.update(e)) : this._$EM();
    } catch (s) {
      throw t = !1, this._$EM(), s;
    }
    t && this._$AE(e);
  }
  willUpdate(t) {
  }
  _$AE(t) {
    this._$EO?.forEach((e) => e.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(t)), this.updated(t);
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
  shouldUpdate(t) {
    return !0;
  }
  update(t) {
    this._$Eq &&= this._$Eq.forEach((e) => this._$ET(e, this[e])), this._$EM();
  }
  updated(t) {
  }
  firstUpdated(t) {
  }
};
A.elementStyles = [], A.shadowRootOptions = { mode: "open" }, A[C("elementProperties")] = /* @__PURE__ */ new Map(), A[C("finalized")] = /* @__PURE__ */ new Map(), Pt?.({ ReactiveElement: A }), (j.reactiveElementVersions ??= []).push("2.1.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const V = globalThis, it = (r) => r, z = V.trustedTypes, rt = z ? z.createPolicy("lit-html", { createHTML: (r) => r }) : void 0, pt = "$lit$", m = `lit$${Math.random().toFixed(9).slice(2)}$`, ut = "?" + m, Ot = `<${ut}>`, y = document, P = () => y.createComment(""), O = (r) => r === null || typeof r != "object" && typeof r != "function", Z = Array.isArray, Ut = (r) => Z(r) || typeof r?.[Symbol.iterator] == "function", L = `[
\f\r]`, w = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, ot = /-->/g, nt = />/g, _ = RegExp(`>|${L}(?:([^\\s"'>=/]+)(${L}*=${L}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`, "g"), at = /'/g, lt = /"/g, $t = /^(?:script|style|textarea|title)$/i, Nt = (r) => (t, ...e) => ({ _$litType$: r, strings: t, values: e }), S = Nt(1), x = Symbol.for("lit-noChange"), u = Symbol.for("lit-nothing"), ct = /* @__PURE__ */ new WeakMap(), g = y.createTreeWalker(y, 129);
function ft(r, t) {
  if (!Z(r) || !r.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return rt !== void 0 ? rt.createHTML(t) : t;
}
const Ht = (r, t) => {
  const e = r.length - 1, s = [];
  let i, o = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", n = w;
  for (let l = 0; l < e; l++) {
    const a = r[l];
    let d, c, h = -1, $ = 0;
    for (; $ < a.length && (n.lastIndex = $, c = n.exec(a), c !== null); ) $ = n.lastIndex, n === w ? c[1] === "!--" ? n = ot : c[1] !== void 0 ? n = nt : c[2] !== void 0 ? ($t.test(c[2]) && (i = RegExp("</" + c[2], "g")), n = _) : c[3] !== void 0 && (n = _) : n === _ ? c[0] === ">" ? (n = i ?? w, h = -1) : c[1] === void 0 ? h = -2 : (h = n.lastIndex - c[2].length, d = c[1], n = c[3] === void 0 ? _ : c[3] === '"' ? lt : at) : n === lt || n === at ? n = _ : n === ot || n === nt ? n = w : (n = _, i = void 0);
    const f = n === _ && r[l + 1].startsWith("/>") ? " " : "";
    o += n === w ? a + Ot : h >= 0 ? (s.push(d), a.slice(0, h) + pt + a.slice(h) + m + f) : a + m + (h === -2 ? l : f);
  }
  return [ft(r, o + (r[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), s];
};
class U {
  constructor({ strings: t, _$litType$: e }, s) {
    let i;
    this.parts = [];
    let o = 0, n = 0;
    const l = t.length - 1, a = this.parts, [d, c] = Ht(t, e);
    if (this.el = U.createElement(d, s), g.currentNode = this.el.content, e === 2 || e === 3) {
      const h = this.el.content.firstChild;
      h.replaceWith(...h.childNodes);
    }
    for (; (i = g.nextNode()) !== null && a.length < l; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const h of i.getAttributeNames()) if (h.endsWith(pt)) {
          const $ = c[n++], f = i.getAttribute(h).split(m), b = /([.?@])?(.*)/.exec($);
          a.push({ type: 1, index: o, name: b[2], strings: f, ctor: b[1] === "." ? Rt : b[1] === "?" ? Tt : b[1] === "@" ? Dt : B }), i.removeAttribute(h);
        } else h.startsWith(m) && (a.push({ type: 6, index: o }), i.removeAttribute(h));
        if ($t.test(i.tagName)) {
          const h = i.textContent.split(m), $ = h.length - 1;
          if ($ > 0) {
            i.textContent = z ? z.emptyScript : "";
            for (let f = 0; f < $; f++) i.append(h[f], P()), g.nextNode(), a.push({ type: 2, index: ++o });
            i.append(h[$], P());
          }
        }
      } else if (i.nodeType === 8) if (i.data === ut) a.push({ type: 2, index: o });
      else {
        let h = -1;
        for (; (h = i.data.indexOf(m, h + 1)) !== -1; ) a.push({ type: 7, index: o }), h += m.length - 1;
      }
      o++;
    }
  }
  static createElement(t, e) {
    const s = y.createElement("template");
    return s.innerHTML = t, s;
  }
}
function E(r, t, e = r, s) {
  if (t === x) return t;
  let i = s !== void 0 ? e._$Co?.[s] : e._$Cl;
  const o = O(t) ? void 0 : t._$litDirective$;
  return i?.constructor !== o && (i?._$AO?.(!1), o === void 0 ? i = void 0 : (i = new o(r), i._$AT(r, e, s)), s !== void 0 ? (e._$Co ??= [])[s] = i : e._$Cl = i), i !== void 0 && (t = E(r, i._$AS(r, t.values), i, s)), t;
}
class kt {
  constructor(t, e) {
    this._$AV = [], this._$AN = void 0, this._$AD = t, this._$AM = e;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t) {
    const { el: { content: e }, parts: s } = this._$AD, i = (t?.creationScope ?? y).importNode(e, !0);
    g.currentNode = i;
    let o = g.nextNode(), n = 0, l = 0, a = s[0];
    for (; a !== void 0; ) {
      if (n === a.index) {
        let d;
        a.type === 2 ? d = new H(o, o.nextSibling, this, t) : a.type === 1 ? d = new a.ctor(o, a.name, a.strings, this, t) : a.type === 6 && (d = new zt(o, this, t)), this._$AV.push(d), a = s[++l];
      }
      n !== a?.index && (o = g.nextNode(), n++);
    }
    return g.currentNode = y, i;
  }
  p(t) {
    let e = 0;
    for (const s of this._$AV) s !== void 0 && (s.strings !== void 0 ? (s._$AI(t, s, e), e += s.strings.length - 2) : s._$AI(t[e])), e++;
  }
}
class H {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t, e, s, i) {
    this.type = 2, this._$AH = u, this._$AN = void 0, this._$AA = t, this._$AB = e, this._$AM = s, this.options = i, this._$Cv = i?.isConnected ?? !0;
  }
  get parentNode() {
    let t = this._$AA.parentNode;
    const e = this._$AM;
    return e !== void 0 && t?.nodeType === 11 && (t = e.parentNode), t;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t, e = this) {
    t = E(this, t, e), O(t) ? t === u || t == null || t === "" ? (this._$AH !== u && this._$AR(), this._$AH = u) : t !== this._$AH && t !== x && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : Ut(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== u && O(this._$AH) ? this._$AA.nextSibling.data = t : this.T(y.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: s } = t, i = typeof s == "number" ? this._$AC(t) : (s.el === void 0 && (s.el = U.createElement(ft(s.h, s.h[0]), this.options)), s);
    if (this._$AH?._$AD === i) this._$AH.p(e);
    else {
      const o = new kt(i, this), n = o.u(this.options);
      o.p(e), this.T(n), this._$AH = o;
    }
  }
  _$AC(t) {
    let e = ct.get(t.strings);
    return e === void 0 && ct.set(t.strings, e = new U(t)), e;
  }
  k(t) {
    Z(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let s, i = 0;
    for (const o of t) i === e.length ? e.push(s = new H(this.O(P()), this.O(P()), this, this.options)) : s = e[i], s._$AI(o), i++;
    i < e.length && (this._$AR(s && s._$AB.nextSibling, i), e.length = i);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const s = it(t).nextSibling;
      it(t).remove(), t = s;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class B {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t, e, s, i, o) {
    this.type = 1, this._$AH = u, this._$AN = void 0, this.element = t, this.name = e, this._$AM = i, this.options = o, s.length > 2 || s[0] !== "" || s[1] !== "" ? (this._$AH = Array(s.length - 1).fill(new String()), this.strings = s) : this._$AH = u;
  }
  _$AI(t, e = this, s, i) {
    const o = this.strings;
    let n = !1;
    if (o === void 0) t = E(this, t, e, 0), n = !O(t) || t !== this._$AH && t !== x, n && (this._$AH = t);
    else {
      const l = t;
      let a, d;
      for (t = o[0], a = 0; a < o.length - 1; a++) d = E(this, l[s + a], e, a), d === x && (d = this._$AH[a]), n ||= !O(d) || d !== this._$AH[a], d === u ? t = u : t !== u && (t += (d ?? "") + o[a + 1]), this._$AH[a] = d;
    }
    n && !i && this.j(t);
  }
  j(t) {
    t === u ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class Rt extends B {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === u ? void 0 : t;
  }
}
class Tt extends B {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== u);
  }
}
class Dt extends B {
  constructor(t, e, s, i, o) {
    super(t, e, s, i, o), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = E(this, t, e, 0) ?? u) === x) return;
    const s = this._$AH, i = t === u && s !== u || t.capture !== s.capture || t.once !== s.once || t.passive !== s.passive, o = t !== u && (s === u || i);
    i && this.element.removeEventListener(this.name, this, s), o && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class zt {
  constructor(t, e, s) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = s;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    E(this, t);
  }
}
const jt = V.litHtmlPolyfillSupport;
jt?.(U, H), (V.litHtmlVersions ??= []).push("3.3.2");
const Bt = (r, t, e) => {
  const s = e?.renderBefore ?? t;
  let i = s._$litPart$;
  if (i === void 0) {
    const o = e?.renderBefore ?? null;
    s._$litPart$ = i = new H(t.insertBefore(P(), o), o, void 0, e ?? {});
  }
  return i._$AI(r), i;
};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const J = globalThis;
class M extends A {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const t = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= t.firstChild, t;
  }
  update(t) {
    const e = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = Bt(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return x;
  }
}
M._$litElement$ = !0, M.finalized = !0, J.litElementHydrateSupport?.({ LitElement: M });
const Lt = J.litElementPolyfillSupport;
Lt?.({ LitElement: M });
(J.litElementVersions ??= []).push("4.2.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const It = (r) => (t, e) => {
  e !== void 0 ? e.addInitializer(() => {
    customElements.define(r, t);
  }) : customElements.define(r, t);
};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const Wt = { attribute: !0, type: String, converter: D, reflect: !1, hasChanged: F }, qt = (r = Wt, t, e) => {
  const { kind: s, metadata: i } = e;
  let o = globalThis.litPropertyMetadata.get(i);
  if (o === void 0 && globalThis.litPropertyMetadata.set(i, o = /* @__PURE__ */ new Map()), s === "setter" && ((r = Object.create(r)).wrapped = !0), o.set(e.name, r), s === "accessor") {
    const { name: n } = e;
    return { set(l) {
      const a = t.get.call(this);
      t.set.call(this, l), this.requestUpdate(n, a, r, !0, l);
    }, init(l) {
      return l !== void 0 && this.C(n, void 0, r, l), l;
    } };
  }
  if (s === "setter") {
    const { name: n } = e;
    return function(l) {
      const a = this[n];
      t.call(this, l), this.requestUpdate(n, a, r, !0, l);
    };
  }
  throw Error("Unsupported decorator location: " + s);
};
function mt(r) {
  return (t, e) => typeof e == "object" ? qt(r, t, e) : ((s, i, o) => {
    const n = i.hasOwnProperty(o);
    return i.constructor.createProperty(o, s), n ? Object.getOwnPropertyDescriptor(i, o) : void 0;
  })(r, t, e);
}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
function Ft(r) {
  return mt({ ...r, state: !0, attribute: !1 });
}
var Vt = Object.defineProperty, Zt = Object.getOwnPropertyDescriptor, K = (r, t, e, s) => {
  for (var i = s > 1 ? void 0 : s ? Zt(t, e) : t, o = r.length - 1, n; o >= 0; o--)
    (n = r[o]) && (i = (s ? n(t, e, i) : n(i)) || i);
  return s && i && Vt(t, e, i), i;
};
function k(r) {
  if (!r) return 0;
  const t = parseFloat(r.state);
  return isNaN(t) ? 0 : t;
}
function v(r) {
  return Math.abs(r) >= 1e3 ? `${(r / 1e3).toFixed(2)} kW` : `${r.toFixed(0)} W`;
}
function ht(r) {
  return {
    normal: "Normal",
    storm: "Tempête",
    vacation: "Vacances (non implémenté)",
    self_consumption: "Auto-conso",
    cost_min: "Coût min",
    revenue_max: "Revenu max",
    peak_shaving: "Écrêtage",
    backup: "Secours",
    longevity: "Longévité",
    manual_override: "Manuel",
    degraded: "Dégradé",
    paused: "Pause"
  }[r] ?? r;
}
const T = 90, I = 44;
function Jt(r, t, e) {
  const s = Math.max(0, r), i = Math.max(0, t), o = Math.max(0, -t), n = Math.max(0, e), l = Math.max(0, -e), a = Math.max(
    0,
    s + i + l - n - o
  ), d = [
    { id: "pv", label: "Solaire", x: 20, y: 20 },
    { id: "battery", label: "Batterie", x: 200, y: 130 },
    { id: "home", label: "Maison", x: 380, y: 20 },
    { id: "grid", label: "Réseau", x: 200, y: 20 }
  ], c = [];
  return s > 0 && a > 0 && c.push({ from: "pv", to: "home", value: Math.min(s, a) }), s > 0 && n > 0 && c.push({ from: "pv", to: "battery", value: n }), s > 0 && o > 0 && c.push({ from: "pv", to: "grid", value: o }), i > 0 && c.push({ from: "grid", to: "home", value: i }), l > 0 && c.push({ from: "battery", to: "home", value: l }), { nodes: d, links: c };
}
function Kt(r, t, e) {
  const s = r.x + T, i = r.y + I / 2, o = t.x, n = t.y + I / 2, l = (s + o) / 2, a = r.id === "grid" ? "var(--warning-color, #ff9800)" : r.id === "battery" ? "var(--info-color, #03a9f4)" : "var(--success-color, #4caf50)";
  return S`<path
    d="M${s},${i} C${l},${i} ${l},${n} ${o},${n}"
    fill="none"
    stroke="${a}"
    stroke-width="${Math.max(2, e)}"
    stroke-opacity="0.7"
  />`;
}
let N = class extends M {
  setConfig(r) {
    this._config = r;
  }
  getCardSize() {
    return 4;
  }
  _entity(r, t) {
    const e = this._config?.[r] ?? t;
    return this.hass?.states[e];
  }
  render() {
    if (!this._config || !this.hass) return S``;
    const r = this._entity("mode_entity", "sensor.solarbalance_mode"), t = this._entity(
      "strategy_entity",
      "sensor.solarbalance_dominant_strategy"
    ), e = this._entity(
      "grid_power_entity",
      "sensor.solarbalance_grid_power"
    ), s = this._entity(
      "pv_power_entity",
      "sensor.solarbalance_pv_power"
    ), i = this._entity(
      "battery_power_entity",
      "sensor.solarbalance_battery_power"
    ), o = this._entity(
      "battery_soc_entity",
      "sensor.solarbalance_battery_soc_avg"
    ), n = r?.state ?? "unknown", l = t?.state ?? "", a = k(e), d = k(s), c = k(i), h = k(o), { nodes: $, links: f } = Jt(d, a, c), b = Math.max(1, ...f.map((p) => p.value)), _t = (p) => p / b * 14 + 2, Y = new Map($.map((p) => [p.id, p])), vt = this._config.title ?? "SolarBalance";
    return S`
      <ha-card>
        <div class="header">
          <span class="title">${vt}</span>
          <span class="mode-badge ${n}">${ht(n)}</span>
        </div>

        <svg
          class="sankey-svg"
          viewBox="0 0 520 200"
          preserveAspectRatio="xMidYMid meet"
        >
          ${f.map((p) => {
      const G = Y.get(p.from), Q = Y.get(p.to);
      return !G || !Q ? u : Kt(G, Q, _t(p.value));
    })}
          ${$.map(
      (p) => S`
              <rect
                class="node-rect"
                x="${p.x}"
                y="${p.y}"
                width="${T}"
                height="${I}"
                fill="var(--card-background-color)"
                stroke="var(--divider-color)"
                stroke-width="1.5"
                rx="6"
                ry="6"
              />
              <text class="node-label" x="${p.x + T / 2}" y="${p.y + 14}">
                ${p.label}
              </text>
              <text class="node-value" x="${p.x + T / 2}" y="${p.y + 30}">
                ${p.id === "pv" ? v(d) : p.id === "grid" ? v(Math.abs(a)) : p.id === "battery" ? v(Math.abs(c)) : v(
        Math.max(
          0,
          d + Math.max(0, -a) + Math.max(0, -c)
        )
      )}
              </text>
            `
    )}
        </svg>

        <div class="metrics">
          <div class="metric">
            <div class="metric-label">Solaire</div>
            <div class="metric-value positive">${v(d)}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Réseau</div>
            <div class="metric-value ${a > 0 ? "negative" : "positive"}">
              ${a > 0 ? "+" : ""}${v(a)}
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">Batterie</div>
            <div class="metric-value ${c < 0 ? "positive" : "negative"}">
              ${c >= 0 ? "Charge" : "Décharge"} ${v(Math.abs(c))}
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">SoC batterie</div>
            <div class="metric-value">${h.toFixed(0)} %</div>
            <div class="soc-bar-bg">
              <div
                class="soc-bar-fill"
                style="width: ${Math.min(100, h).toFixed(0)}%"
              ></div>
            </div>
          </div>
          ${l ? S`<div class="metric">
                <div class="metric-label">Stratégie</div>
                <div class="metric-value">${ht(l)}</div>
              </div>` : u}
        </div>
      </ha-card>
    `;
  }
};
N.styles = yt`
    :host {
      display: block;
    }
    ha-card {
      padding: 16px;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .title {
      font-size: 1.1em;
      font-weight: 600;
    }
    .mode-badge {
      font-size: 0.8em;
      padding: 2px 8px;
      border-radius: 12px;
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .mode-badge.degraded {
      background: var(--error-color, #f44336);
    }
    .mode-badge.paused {
      background: var(--disabled-color, #9e9e9e);
    }
    .sankey-svg {
      width: 100%;
      height: 220px;
    }
    .node-rect {
      rx: 6;
      ry: 6;
    }
    .node-label {
      font-size: 11px;
      fill: var(--primary-text-color);
      text-anchor: middle;
      dominant-baseline: middle;
    }
    .node-value {
      font-size: 10px;
      fill: var(--secondary-text-color);
      text-anchor: middle;
      dominant-baseline: middle;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
      gap: 8px;
      margin-top: 12px;
    }
    .metric {
      text-align: center;
      padding: 8px;
      border-radius: 8px;
      background: var(--secondary-background-color);
    }
    .metric-label {
      font-size: 0.75em;
      color: var(--secondary-text-color);
    }
    .metric-value {
      font-size: 1em;
      font-weight: 600;
      margin-top: 2px;
    }
    .metric-value.positive {
      color: var(--success-color, #4caf50);
    }
    .metric-value.negative {
      color: var(--warning-color, #ff9800);
    }
    .soc-bar-bg {
      height: 6px;
      border-radius: 3px;
      background: var(--divider-color);
      margin-top: 4px;
      overflow: hidden;
    }
    .soc-bar-fill {
      height: 100%;
      border-radius: 3px;
      background: var(--info-color, #03a9f4);
      transition: width 0.4s ease;
    }
  `;
K([
  mt({ attribute: !1 })
], N.prototype, "hass", 2);
K([
  Ft()
], N.prototype, "_config", 2);
N = K([
  It("solarbalance-card")
], N);
window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "solarbalance-card",
  name: "SolarBalance Card",
  description: "Flux d'énergie temps réel (solaire / batterie / réseau / maison) avec indicateurs HEMS.",
  preview: !0
});
export {
  N as SolarBalanceCard
};
