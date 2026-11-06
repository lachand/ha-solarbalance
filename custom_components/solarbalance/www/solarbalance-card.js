/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const B = globalThis, Q = B.ShadowRoot && (B.ShadyCSS === void 0 || B.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, X = Symbol(), ne = /* @__PURE__ */ new WeakMap();
let be = class {
  constructor(e, t, s) {
    if (this._$cssResult$ = !0, s !== X) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = e, this.t = t;
  }
  get styleSheet() {
    let e = this.o;
    const t = this.t;
    if (Q && e === void 0) {
      const s = t !== void 0 && t.length === 1;
      s && (e = ne.get(t)), e === void 0 && ((this.o = e = new CSSStyleSheet()).replaceSync(this.cssText), s && ne.set(t, e));
    }
    return e;
  }
  toString() {
    return this.cssText;
  }
};
const Le = (r) => new be(typeof r == "string" ? r : r + "", void 0, X), Re = (r, ...e) => {
  const t = r.length === 1 ? r[0] : e.reduce((s, i, a) => s + ((n) => {
    if (n._$cssResult$ === !0) return n.cssText;
    if (typeof n == "number") return n;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + n + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(i) + r[a + 1], r[0]);
  return new be(t, r, X);
}, De = (r, e) => {
  if (Q) r.adoptedStyleSheets = e.map((t) => t instanceof CSSStyleSheet ? t : t.styleSheet);
  else for (const t of e) {
    const s = document.createElement("style"), i = B.litNonce;
    i !== void 0 && s.setAttribute("nonce", i), s.textContent = t.cssText, r.appendChild(s);
  }
}, ae = Q ? (r) => r : (r) => r instanceof CSSStyleSheet ? ((e) => {
  let t = "";
  for (const s of e.cssRules) t += s.cssText;
  return Le(t);
})(r) : r;
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const { is: Ie, defineProperty: Be, getOwnPropertyDescriptor: je, getOwnPropertyNames: qe, getOwnPropertySymbols: ze, getPrototypeOf: Fe } = Object, F = globalThis, oe = F.trustedTypes, We = oe ? oe.emptyScript : "", Ve = F.reactiveElementPolyfillSupport, k = (r, e) => r, j = { toAttribute(r, e) {
  switch (e) {
    case Boolean:
      r = r ? We : null;
      break;
    case Object:
    case Array:
      r = r == null ? r : JSON.stringify(r);
  }
  return r;
}, fromAttribute(r, e) {
  let t = r;
  switch (e) {
    case Boolean:
      t = r !== null;
      break;
    case Number:
      t = r === null ? null : Number(r);
      break;
    case Object:
    case Array:
      try {
        t = JSON.parse(r);
      } catch {
        t = null;
      }
  }
  return t;
} }, ee = (r, e) => !Ie(r, e), le = { attribute: !0, type: String, converter: j, reflect: !1, useDefault: !1, hasChanged: ee };
Symbol.metadata ??= Symbol("metadata"), F.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let A = class extends HTMLElement {
  static addInitializer(e) {
    this._$Ei(), (this.l ??= []).push(e);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(e, t = le) {
    if (t.state && (t.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(e) && ((t = Object.create(t)).wrapped = !0), this.elementProperties.set(e, t), !t.noAccessor) {
      const s = Symbol(), i = this.getPropertyDescriptor(e, s, t);
      i !== void 0 && Be(this.prototype, e, i);
    }
  }
  static getPropertyDescriptor(e, t, s) {
    const { get: i, set: a } = je(this.prototype, e) ?? { get() {
      return this[t];
    }, set(n) {
      this[t] = n;
    } };
    return { get: i, set(n) {
      const l = i?.call(this);
      a?.call(this, n), this.requestUpdate(e, l, s);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(e) {
    return this.elementProperties.get(e) ?? le;
  }
  static _$Ei() {
    if (this.hasOwnProperty(k("elementProperties"))) return;
    const e = Fe(this);
    e.finalize(), e.l !== void 0 && (this.l = [...e.l]), this.elementProperties = new Map(e.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(k("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(k("properties"))) {
      const t = this.properties, s = [...qe(t), ...ze(t)];
      for (const i of s) this.createProperty(i, t[i]);
    }
    const e = this[Symbol.metadata];
    if (e !== null) {
      const t = litPropertyMetadata.get(e);
      if (t !== void 0) for (const [s, i] of t) this.elementProperties.set(s, i);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [t, s] of this.elementProperties) {
      const i = this._$Eu(t, s);
      i !== void 0 && this._$Eh.set(i, t);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(e) {
    const t = [];
    if (Array.isArray(e)) {
      const s = new Set(e.flat(1 / 0).reverse());
      for (const i of s) t.unshift(ae(i));
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
    return De(e, this.constructor.elementStyles), e;
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
    const s = this.constructor.elementProperties.get(e), i = this.constructor._$Eu(e, s);
    if (i !== void 0 && s.reflect === !0) {
      const a = (s.converter?.toAttribute !== void 0 ? s.converter : j).toAttribute(t, s.type);
      this._$Em = e, a == null ? this.removeAttribute(i) : this.setAttribute(i, a), this._$Em = null;
    }
  }
  _$AK(e, t) {
    const s = this.constructor, i = s._$Eh.get(e);
    if (i !== void 0 && this._$Em !== i) {
      const a = s.getPropertyOptions(i), n = typeof a.converter == "function" ? { fromAttribute: a.converter } : a.converter?.fromAttribute !== void 0 ? a.converter : j;
      this._$Em = i;
      const l = n.fromAttribute(t, a.type);
      this[i] = l ?? this._$Ej?.get(i) ?? l, this._$Em = null;
    }
  }
  requestUpdate(e, t, s, i = !1, a) {
    if (e !== void 0) {
      const n = this.constructor;
      if (i === !1 && (a = this[e]), s ??= n.getPropertyOptions(e), !((s.hasChanged ?? ee)(a, t) || s.useDefault && s.reflect && a === this._$Ej?.get(e) && !this.hasAttribute(n._$Eu(e, s)))) return;
      this.C(e, t, s);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(e, t, { useDefault: s, reflect: i, wrapped: a }, n) {
    s && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(e) && (this._$Ej.set(e, n ?? t ?? this[e]), a !== !0 || n !== void 0) || (this._$AL.has(e) || (this.hasUpdated || s || (t = void 0), this._$AL.set(e, t)), i === !0 && this._$Em !== e && (this._$Eq ??= /* @__PURE__ */ new Set()).add(e));
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
        for (const [i, a] of this._$Ep) this[i] = a;
        this._$Ep = void 0;
      }
      const s = this.constructor.elementProperties;
      if (s.size > 0) for (const [i, a] of s) {
        const { wrapped: n } = a, l = this[i];
        n !== !0 || this._$AL.has(i) || l === void 0 || this.C(i, void 0, a, l);
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
A.elementStyles = [], A.shadowRootOptions = { mode: "open" }, A[k("elementProperties")] = /* @__PURE__ */ new Map(), A[k("finalized")] = /* @__PURE__ */ new Map(), Ve?.({ ReactiveElement: A }), (F.reactiveElementVersions ??= []).push("2.1.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const te = globalThis, ce = (r) => r, q = te.trustedTypes, he = q ? q.createPolicy("lit-html", { createHTML: (r) => r }) : void 0, Ae = "$lit$", f = `lit$${Math.random().toFixed(9).slice(2)}$`, Se = "?" + f, Ge = `<${Se}>`, y = document, T = () => y.createComment(""), O = (r) => r === null || typeof r != "object" && typeof r != "function", se = Array.isArray, Ke = (r) => se(r) || typeof r?.[Symbol.iterator] == "function", G = `[ 	
\f\r]`, x = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, ue = /-->/g, de = />/g, v = RegExp(`>|${G}(?:([^\\s"'>=/]+)(${G}*=${G}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), pe = /'/g, me = /"/g, we = /^(?:script|style|textarea|title)$/i, Ze = (r) => (e, ...t) => ({ _$litType$: r, strings: e, values: t }), $e = Ze(1), b = Symbol.for("lit-noChange"), d = Symbol.for("lit-nothing"), ge = /* @__PURE__ */ new WeakMap(), _ = y.createTreeWalker(y, 129);
function Ce(r, e) {
  if (!se(r) || !r.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return he !== void 0 ? he.createHTML(e) : e;
}
const Je = (r, e) => {
  const t = r.length - 1, s = [];
  let i, a = e === 2 ? "<svg>" : e === 3 ? "<math>" : "", n = x;
  for (let l = 0; l < t; l++) {
    const o = r[l];
    let c, u, h = -1, p = 0;
    for (; p < o.length && (n.lastIndex = p, u = n.exec(o), u !== null); ) p = n.lastIndex, n === x ? u[1] === "!--" ? n = ue : u[1] !== void 0 ? n = de : u[2] !== void 0 ? (we.test(u[2]) && (i = RegExp("</" + u[2], "g")), n = v) : u[3] !== void 0 && (n = v) : n === v ? u[0] === ">" ? (n = i ?? x, h = -1) : u[1] === void 0 ? h = -2 : (h = n.lastIndex - u[2].length, c = u[1], n = u[3] === void 0 ? v : u[3] === '"' ? me : pe) : n === me || n === pe ? n = v : n === ue || n === de ? n = x : (n = v, i = void 0);
    const $ = n === v && r[l + 1].startsWith("/>") ? " " : "";
    a += n === x ? o + Ge : h >= 0 ? (s.push(c), o.slice(0, h) + Ae + o.slice(h) + f + $) : o + f + (h === -2 ? l : $);
  }
  return [Ce(r, a + (r[t] || "<?>") + (e === 2 ? "</svg>" : e === 3 ? "</math>" : "")), s];
};
class U {
  constructor({ strings: e, _$litType$: t }, s) {
    let i;
    this.parts = [];
    let a = 0, n = 0;
    const l = e.length - 1, o = this.parts, [c, u] = Je(e, t);
    if (this.el = U.createElement(c, s), _.currentNode = this.el.content, t === 2 || t === 3) {
      const h = this.el.content.firstChild;
      h.replaceWith(...h.childNodes);
    }
    for (; (i = _.nextNode()) !== null && o.length < l; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const h of i.getAttributeNames()) if (h.endsWith(Ae)) {
          const p = u[n++], $ = i.getAttribute(h).split(f), g = /([.?@])?(.*)/.exec(p);
          o.push({ type: 1, index: a, name: g[2], strings: $, ctor: g[1] === "." ? Qe : g[1] === "?" ? Xe : g[1] === "@" ? et : W }), i.removeAttribute(h);
        } else h.startsWith(f) && (o.push({ type: 6, index: a }), i.removeAttribute(h));
        if (we.test(i.tagName)) {
          const h = i.textContent.split(f), p = h.length - 1;
          if (p > 0) {
            i.textContent = q ? q.emptyScript : "";
            for (let $ = 0; $ < p; $++) i.append(h[$], T()), _.nextNode(), o.push({ type: 2, index: ++a });
            i.append(h[p], T());
          }
        }
      } else if (i.nodeType === 8) if (i.data === Se) o.push({ type: 2, index: a });
      else {
        let h = -1;
        for (; (h = i.data.indexOf(f, h + 1)) !== -1; ) o.push({ type: 7, index: a }), h += f.length - 1;
      }
      a++;
    }
  }
  static createElement(e, t) {
    const s = y.createElement("template");
    return s.innerHTML = e, s;
  }
}
function w(r, e, t = r, s) {
  if (e === b) return e;
  let i = s !== void 0 ? t._$Co?.[s] : t._$Cl;
  const a = O(e) ? void 0 : e._$litDirective$;
  return i?.constructor !== a && (i?._$AO?.(!1), a === void 0 ? i = void 0 : (i = new a(r), i._$AT(r, t, s)), s !== void 0 ? (t._$Co ??= [])[s] = i : t._$Cl = i), i !== void 0 && (e = w(r, i._$AS(r, e.values), i, s)), e;
}
class Ye {
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
    const { el: { content: t }, parts: s } = this._$AD, i = (e?.creationScope ?? y).importNode(t, !0);
    _.currentNode = i;
    let a = _.nextNode(), n = 0, l = 0, o = s[0];
    for (; o !== void 0; ) {
      if (n === o.index) {
        let c;
        o.type === 2 ? c = new H(a, a.nextSibling, this, e) : o.type === 1 ? c = new o.ctor(a, o.name, o.strings, this, e) : o.type === 6 && (c = new tt(a, this, e)), this._$AV.push(c), o = s[++l];
      }
      n !== o?.index && (a = _.nextNode(), n++);
    }
    return _.currentNode = y, i;
  }
  p(e) {
    let t = 0;
    for (const s of this._$AV) s !== void 0 && (s.strings !== void 0 ? (s._$AI(e, s, t), t += s.strings.length - 2) : s._$AI(e[t])), t++;
  }
}
class H {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(e, t, s, i) {
    this.type = 2, this._$AH = d, this._$AN = void 0, this._$AA = e, this._$AB = t, this._$AM = s, this.options = i, this._$Cv = i?.isConnected ?? !0;
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
    e = w(this, e, t), O(e) ? e === d || e == null || e === "" ? (this._$AH !== d && this._$AR(), this._$AH = d) : e !== this._$AH && e !== b && this._(e) : e._$litType$ !== void 0 ? this.$(e) : e.nodeType !== void 0 ? this.T(e) : Ke(e) ? this.k(e) : this._(e);
  }
  O(e) {
    return this._$AA.parentNode.insertBefore(e, this._$AB);
  }
  T(e) {
    this._$AH !== e && (this._$AR(), this._$AH = this.O(e));
  }
  _(e) {
    this._$AH !== d && O(this._$AH) ? this._$AA.nextSibling.data = e : this.T(y.createTextNode(e)), this._$AH = e;
  }
  $(e) {
    const { values: t, _$litType$: s } = e, i = typeof s == "number" ? this._$AC(e) : (s.el === void 0 && (s.el = U.createElement(Ce(s.h, s.h[0]), this.options)), s);
    if (this._$AH?._$AD === i) this._$AH.p(t);
    else {
      const a = new Ye(i, this), n = a.u(this.options);
      a.p(t), this.T(n), this._$AH = a;
    }
  }
  _$AC(e) {
    let t = ge.get(e.strings);
    return t === void 0 && ge.set(e.strings, t = new U(e)), t;
  }
  k(e) {
    se(this._$AH) || (this._$AH = [], this._$AR());
    const t = this._$AH;
    let s, i = 0;
    for (const a of e) i === t.length ? t.push(s = new H(this.O(T()), this.O(T()), this, this.options)) : s = t[i], s._$AI(a), i++;
    i < t.length && (this._$AR(s && s._$AB.nextSibling, i), t.length = i);
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
let W = class {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(e, t, s, i, a) {
    this.type = 1, this._$AH = d, this._$AN = void 0, this.element = e, this.name = t, this._$AM = i, this.options = a, s.length > 2 || s[0] !== "" || s[1] !== "" ? (this._$AH = Array(s.length - 1).fill(new String()), this.strings = s) : this._$AH = d;
  }
  _$AI(e, t = this, s, i) {
    const a = this.strings;
    let n = !1;
    if (a === void 0) e = w(this, e, t, 0), n = !O(e) || e !== this._$AH && e !== b, n && (this._$AH = e);
    else {
      const l = e;
      let o, c;
      for (e = a[0], o = 0; o < a.length - 1; o++) c = w(this, l[s + o], t, o), c === b && (c = this._$AH[o]), n ||= !O(c) || c !== this._$AH[o], c === d ? e = d : e !== d && (e += (c ?? "") + a[o + 1]), this._$AH[o] = c;
    }
    n && !i && this.j(e);
  }
  j(e) {
    e === d ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, e ?? "");
  }
};
class Qe extends W {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(e) {
    this.element[this.name] = e === d ? void 0 : e;
  }
}
class Xe extends W {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(e) {
    this.element.toggleAttribute(this.name, !!e && e !== d);
  }
}
class et extends W {
  constructor(e, t, s, i, a) {
    super(e, t, s, i, a), this.type = 5;
  }
  _$AI(e, t = this) {
    if ((e = w(this, e, t, 0) ?? d) === b) return;
    const s = this._$AH, i = e === d && s !== d || e.capture !== s.capture || e.once !== s.once || e.passive !== s.passive, a = e !== d && (s === d || i);
    i && this.element.removeEventListener(this.name, this, s), a && this.element.addEventListener(this.name, this, e), this._$AH = e;
  }
  handleEvent(e) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, e) : this._$AH.handleEvent(e);
  }
}
class tt {
  constructor(e, t, s) {
    this.element = e, this.type = 6, this._$AN = void 0, this._$AM = t, this.options = s;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(e) {
    w(this, e);
  }
}
const st = te.litHtmlPolyfillSupport;
st?.(U, H), (te.litHtmlVersions ??= []).push("3.3.2");
const rt = (r, e, t) => {
  const s = t?.renderBefore ?? e;
  let i = s._$litPart$;
  if (i === void 0) {
    const a = t?.renderBefore ?? null;
    s._$litPart$ = i = new H(e.insertBefore(T(), a), a, void 0, t ?? {});
  }
  return i._$AI(r), i;
};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const re = globalThis;
let N = class extends A {
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
N._$litElement$ = !0, N.finalized = !0, re.litElementHydrateSupport?.({ LitElement: N });
const it = re.litElementPolyfillSupport;
it?.({ LitElement: N });
(re.litElementVersions ??= []).push("4.2.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const nt = (r) => (e, t) => {
  t !== void 0 ? t.addInitializer(() => {
    customElements.define(r, e);
  }) : customElements.define(r, e);
};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const at = { attribute: !0, type: String, converter: j, reflect: !1, hasChanged: ee }, ot = (r = at, e, t) => {
  const { kind: s, metadata: i } = t;
  let a = globalThis.litPropertyMetadata.get(i);
  if (a === void 0 && globalThis.litPropertyMetadata.set(i, a = /* @__PURE__ */ new Map()), s === "setter" && ((r = Object.create(r)).wrapped = !0), a.set(t.name, r), s === "accessor") {
    const { name: n } = t;
    return { set(l) {
      const o = e.get.call(this);
      e.set.call(this, l), this.requestUpdate(n, o, r, !0, l);
    }, init(l) {
      return l !== void 0 && this.C(n, void 0, r, l), l;
    } };
  }
  if (s === "setter") {
    const { name: n } = t;
    return function(l) {
      const o = this[n];
      e.call(this, l), this.requestUpdate(n, o, r, !0, l);
    };
  }
  throw Error("Unsupported decorator location: " + s);
};
function Me(r) {
  return (e, t) => typeof t == "object" ? ot(r, e, t) : ((s, i, a) => {
    const n = i.hasOwnProperty(a);
    return i.constructor.createProperty(a, s), n ? Object.getOwnPropertyDescriptor(i, a) : void 0;
  })(r, e, t);
}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
function Ee(r) {
  return Me({ ...r, state: !0, attribute: !1 });
}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const lt = { CHILD: 2 }, ct = (r) => (...e) => ({ _$litDirective$: r, values: e });
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
class J extends ht {
  constructor(e) {
    if (super(e), this.it = d, e.type !== lt.CHILD) throw Error(this.constructor.directiveName + "() can only be used in child bindings");
  }
  render(e) {
    if (e === d || e == null) return this._t = void 0, this.it = e;
    if (e === b) return e;
    if (typeof e != "string") throw Error(this.constructor.directiveName + "() called with a non-string value");
    if (e === this.it) return this._t;
    this.it = e;
    const t = [e];
    return t.raw = t, this._t = { _$litType$: this.constructor.resultType, strings: t, values: [] };
  }
}
J.directiveName = "unsafeHTML", J.resultType = 1;
const ut = ct(J), dt = {
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
  "Appareils et solaire récupérable": "Appliances and recoverable solar",
  "Apprentissage en cours : aucun cycle complet enregistré.": "Learning: no complete cycle recorded yet.",
  "en cours": "running",
  "peu de cycles": "few cycles",
  "de solaire maintenant": "solar now",
  à: "at",
  "en attendant": "by waiting",
  "Renommer ce programme": "Rename this program",
  "Nouveau nom du programme": "New program name",
  "Nom du cycle que vous venez de lancer (par exemple Coton 40)": "Name the cycle you just ran (for example Cottons 40)",
  "cycle(s) non étiqueté(s)": "unlabelled cycle(s)",
  "Étiqueter le dernier": "Label the last one",
  "Plan indicatif sur 24 h": "Advisory plan, 24 h",
  "Plan indicatif de la batterie sur 24 h": "Advisory battery plan, 24 h",
  "barres pleines, charge prévue ; barres creuses, décharge prévue ; ligne, niveau de charge prévu.": "filled bars, planned charge; outlined bars, planned discharge; line, planned level.",
  "Charge prévue": "Planned charge",
  "Décharge prévue": "Planned discharge",
  "Niveau prévu": "Planned level",
  de: "from",
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
function mt(r, e) {
  const t = `${r}|${e}`;
  let s = fe.get(t);
  return s || (s = new Intl.NumberFormat(r, {
    minimumFractionDigits: e,
    maximumFractionDigits: e
  }), fe.set(t, s)), s;
}
function z(r, e = 0, t = "fr") {
  if (r == null || !Number.isFinite(r)) return "—";
  const s = mt(t, e).format(r);
  return (Number(r.toFixed(e)) === 0 ? s.replace("-", "") : s).replace("-", pt);
}
function Pe(r, e) {
  return e ? `${r}${xe}${e}` : r;
}
function ke(r, e = "fr") {
  return r == null || !Number.isFinite(r) ? { value: "—", unit: "W" } : Math.abs(r) >= 1e3 ? { value: z(r / 1e3, 2, e), unit: "kW" } : { value: z(Math.round(r), 0, e), unit: "W" };
}
function P(r, e = "fr") {
  const t = ke(r, e);
  return t.value === "—" ? "—" : Pe(t.value, t.unit);
}
function m(r) {
  return String(r ?? "").replace(
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
function gt(r) {
  return $t[r] || ["inactif", r || "—"];
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
function Ne(r, e = 16) {
  return `<svg class="ic" viewBox="0 0 24 24" width="${e}" height="${e}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ft[r] || ""}</svg>`;
}
const vt = {
  ok: "ok",
  attention: "attention",
  critique: "critique",
  inactif: "inactif",
  info: "info"
};
function _t(r, e, t = "") {
  const s = t ? ` title="${m(t)}"` : "";
  return `<span class="sg-stamp st-${r}" role="status"${s}>${Ne(vt[r], 14)}<span>${m(e)}</span></span>`;
}
function ve(r, e = "", t = "") {
  const s = e ? `<span class="mu">${m(e)}</span>` : "";
  return `<span class="mesure ${t}"><span class="mv">${r}</span>${s}</span>`;
}
function _e(r, e = "") {
  const t = String(r), s = t.indexOf(" ");
  return s < 0 ? ve(m(t), "", e) : ve(m(t.slice(0, s)), t.slice(s + 1), e);
}
function yt(r, e, t = "") {
  const s = t ? `<div class="tn">${m(t)}</div>` : "";
  return `<div class="tile"><div class="tl">${m(r)}</div>${e}${s}</div>`;
}
function bt(r, e, { tick: t = null, tone: s = "" } = {}) {
  const i = r == null ? 0 : Math.max(0, Math.min(100, r)), a = t != null ? `<span class="bar-tick" style="left:${t}%"></span>` : "", n = r == null ? "" : ` aria-valuenow="${Math.round(i)}"`;
  return `<div class="bar ${s}" role="meter" aria-valuemin="0" aria-valuemax="100"${n} aria-label="${m(e)}"><span class="bar-fill" style="width:${i}%"></span>${a}</div>`;
}
const At = 480, St = 178, ye = 124, K = 66, S = 20, R = {
  pv: { color: "var(--production)", dash: "", marker: "ah-pv" },
  grid: { color: "var(--consommation)", dash: "8 5", marker: "ah-grid" },
  batt: { color: "var(--stockage)", dash: "1.5 5", marker: "ah-batt", round: !0 }
};
function Z(r, e, t) {
  const s = Math.abs(e || 0);
  if (s < S) return `<path d="${r}" class="flow-off"/>`;
  const i = Math.max(2, Math.min(7, 2 + s / 400)).toFixed(1), a = Math.max(0.6, 2 - s / 1e3).toFixed(2), n = t.dash ? ` stroke-dasharray="${t.dash}"` : "", l = t.round ? ' stroke-linecap="round"' : "", o = e > 0, c = o ? `marker-end="url(#${t.marker})"` : `marker-start="url(#${t.marker})"`, u = t.dash ? ` class="flow-anim ${o ? "in" : "out"}" style="animation-duration:${a}s"` : "";
  return `<path d="${r}" fill="none" stroke="${t.color}" stroke-width="${i}"${n}${l} ${c}${u}/>`;
}
function D(r, e, t, s, i, a, n, l) {
  const o = r - ye / 2, c = e - K / 2, u = ke(i, l);
  return `
    <g class="flow-node">
      <rect x="${o}" y="${c}" width="${ye}" height="${K}" rx="2" class="fn-box"/>
      <rect x="${o}" y="${c}" width="3" height="${K}" fill="${n}"/>
      <g transform="translate(${o + 10} ${c + 10})" style="color:${n}">${Ne(t, 20)}</g>
      <text x="${o + 38}" y="${c + 20}" class="fn-lbl">${m(s)}</text>
      <text x="${o + 38}" y="${c + 42}"><tspan class="fn-val">${m(u.value)}</tspan><tspan class="fn-unit" dx="3">${u.unit}</tspan></text>
      <text x="${o + 38}" y="${c + 59}" class="fn-sub">${m(a)}</text>
    </g>`;
}
function wt(r) {
  const { pv: e, grid: t, batt: s, home: i, soc: a, lang: n, t: l } = r, o = t > S ? "Soutirage" : t < -S ? "Injection" : "Équilibre", c = s > S ? "charge" : s < -S ? "décharge" : "repos", u = a != null ? `${z(Math.round(a), 0, n)}${xe}% · ${l(c)}` : l(c), h = e >= S ? "Production" : "Au repos", p = 141, $ = Z("M240 68 L240 108", e, R.pv) + Z(`M126 ${p} L178 ${p}`, t, R.grid) + Z(`M354 ${p} L302 ${p}`, -s, R.batt), g = Object.values(R).map(
    (L) => `<marker id="${L.marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${L.color}"/></marker>`
  ).join(""), M = `${l("Flux d'énergie")} : ${l("solaire")} ${P(e, n)}, ${l("réseau")} ${P(t, n)} (${l(o).toLowerCase()}), ${l("batteries")} ${P(s, n)} (${l(c)}), ${l("maison")} ${P(i, n)}`;
  return `
    <svg viewBox="0 0 ${At} ${St}" class="flow" role="img" aria-label="${m(M)}">
      <defs>${g}</defs>
      ${$}
      ${D(240, 35, "sun", l("Solaire"), e, l(h), "var(--production)", n)}
      ${D(64, p, "grid", l("Réseau"), t, l(o), "var(--consommation)", n)}
      ${D(416, p, "battery", l("Batteries"), s, u, "var(--stockage)", n)}
      ${D(240, p, "home", l("Maison"), i, l("Consommation"), "var(--ink)", n)}
    </svg>`;
}
var Ct = Object.defineProperty, Mt = Object.getOwnPropertyDescriptor, V = (r, e, t, s) => {
  for (var i = s > 1 ? void 0 : s ? Mt(e, t) : e, a = r.length - 1, n; a >= 0; a--)
    (n = r[a]) && (i = (s ? n(e, t, i) : n(i)) || i);
  return s && i && Ct(e, t, i), i;
};
const Et = {
  mode_entity: ["mode", "sensor.solarbalance_mode"],
  strategy_entity: ["dominant_strategy", "sensor.solarbalance_dominant_strategy"],
  grid_power_entity: ["grid_power", "sensor.solarbalance_grid_power"],
  pv_power_entity: ["pv_power", "sensor.solarbalance_pv_power"],
  battery_power_entity: ["battery_power", "sensor.solarbalance_battery_power"],
  battery_soc_entity: ["battery_soc_avg", "sensor.solarbalance_battery_soc_avg"]
}, Y = new URL(
  /* @vite-ignore */
  "vendor/signature/",
  import.meta.url
).href, xt = new URL(
  /* @vite-ignore */
  "panel/panel.css",
  import.meta.url
).href, Pt = {
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
function I(r) {
  if (!r || r.state === "unavailable" || r.state === "unknown") return null;
  const e = parseFloat(r.state);
  return Number.isNaN(e) ? null : e;
}
function kt() {
  if (document.getElementById("sb-signature-fonts")) return;
  const r = document.createElement("link");
  r.id = "sb-signature-fonts", r.rel = "stylesheet", r.href = `${Y}fonts.css`, document.head.appendChild(r);
}
let C = class extends N {
  constructor() {
    super(...arguments), this._ready = !1;
  }
  connectedCallback() {
    super.connectedCallback(), kt(), window.setTimeout(() => this._ready = !0, 1500);
  }
  setConfig(r) {
    this._config = r;
  }
  getCardSize() {
    return 5;
  }
  /** Resolve an entity: explicit config, then translation_key (localised ids), then default id. */
  _entity(r) {
    const e = this.hass;
    if (!e) return;
    const t = this._config?.[r];
    if (t) return e.states[t];
    const [s, i] = Et[r];
    for (const [a, n] of Object.entries(e.entities ?? {}))
      if (n.platform === "solarbalance" && n.translation_key === s) return e.states[a];
    return e.states[i];
  }
  render() {
    if (!this._config || !this.hass) return $e``;
    const r = this.hass, e = r.locale?.language || r.language || "fr", t = e.startsWith("en"), s = (E) => t ? dt[E] ?? E : E, i = this._entity("mode_entity"), a = this._entity("strategy_entity")?.state ?? "", n = I(this._entity("grid_power_entity")), l = I(this._entity("pv_power_entity")), o = I(this._entity("battery_power_entity")), c = I(this._entity("battery_soc_entity")), u = Math.max(0, (l ?? 0) + (n ?? 0) - (o ?? 0)), [h, p] = gt(i?.state), $ = this._config.contrast ? "contrast" : r.themes?.darkMode ? "dark" : "light", g = this._config.title ?? "SolarBalance", M = (E, ie, He = "") => ie == null ? "" : yt(s(E), _e(P(ie, e)), He), L = n == null ? "" : n > 20 ? s("Soutirage") : n < -20 ? s("Injection") : "", Te = o == null ? "" : o > 20 ? s("Charge") : o < -20 ? s("Décharge") : "", Oe = c == null ? "" : `<div class="tile"><div class="tl">${m(s("Niveau moyen"))}</div>${_e(
      Pe(z(Math.round(c), 0, e), "%")
    )}</div>`, Ue = `
      <div class="card-h"><h3 class="cote-rule">${m(g)}</h3>${_t(h, s(p))}</div>
      ${wt({ pv: l ?? 0, grid: n ?? 0, batt: o ?? 0, home: u, soc: c, lang: e, t: s })}
      <div class="tiles sbc-foot">
        ${M("Solaire", l)}${M("Réseau", n, L)}${M("Batteries", o, Te)}${Oe}
      </div>
      ${c == null ? "" : `<div class="sbc-foot">${bt(c, s("Niveau de charge"))}</div>`}
      ${a ? `<p class="note">${m(s("Stratégie"))} : ${m(Pt[a] ?? a)}</p>` : ""}`;
    return $e`
      <link rel="stylesheet" href="${Y}tokens.scoped.css" />
      <link rel="stylesheet" href="${Y}overlay.css" />
      <link
        rel="stylesheet"
        href="${xt}"
        @load=${() => this._ready = !0}
      />
      <div class="sg-scope sbc-root ${this._ready ? "ready" : ""}" data-theme="${$}">
        <section class="card">${ut(Ue)}</section>
      </div>
    `;
  }
};
C.styles = Re`
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
V([
  Me({ attribute: !1 })
], C.prototype, "hass", 2);
V([
  Ee()
], C.prototype, "_config", 2);
V([
  Ee()
], C.prototype, "_ready", 2);
C = V([
  nt("solarbalance-card")
], C);
window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "solarbalance-card",
  name: "SolarBalance",
  description: "Flux d'énergie en temps réel (solaire, batteries, réseau, maison) et état du pilotage.",
  preview: !0
});
export {
  C as SolarBalanceCard
};
