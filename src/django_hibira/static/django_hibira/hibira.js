/*! django-hibira | MIT | https://hibira.io */
// Live HTML over Hibira.
//
// {% hibira_stream room %} renders <hibira-stream>. Each one subscribes to
// its stream's private channel and applies every operation the server
// broadcasts (append, prepend, replace, update, before, after, remove,
// refresh) to this page. window.Hibira.client() is the shared pusher-js
// client, for your own channels.
;(function () {
  "use strict"

  var EVENT = "html-swap"
  var UNSUBSCRIBE_DELAY = 1000 // keeps the channel when the same stream is re-rendered
  var client = null
  var streams = new Map() // channel name -> { channel, elements, signed, timer }
  var refreshTimer = null

  function meta(name) {
    var el = document.querySelector('meta[name="' + name + '"]')
    return el ? el.content : null
  }

  function csrfToken() {
    var token = meta("hibira-csrf-token")
    if (token) return token
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
    return match ? decodeURIComponent(match[1]) : null
  }

  function authorize(params, callback) {
    var stream = streams.get(params.channelName)
    var body = new URLSearchParams({ socket_id: params.socketId, channel_name: params.channelName })
    var endpoint
    var headers = { Accept: "application/json" }
    if (stream) {
      endpoint = meta("hibira-stream-auth-endpoint") || "/hibira/streams/auth"
      body.set("signed_stream_name", stream.signed)
    } else {
      endpoint = meta("hibira-auth-endpoint") || "/hibira/auth"
      var token = csrfToken()
      if (token) headers["X-CSRFToken"] = token
    }
    fetch(endpoint, { method: "POST", headers: headers, body: body, credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("Hibira auth for " + params.channelName + " failed with " + response.status)
        return response.json()
      })
      .then(function (data) { callback(null, data) })
      .catch(function (error) { callback(error, null) })
  }

  function getClient() {
    if (client) return client
    if (typeof window.Pusher !== "function") {
      throw new Error("Hibira: pusher-js is not loaded. Use {% hibira_scripts %}, or load pusher-js before django_hibira/hibira.js.")
    }
    var key = meta("hibira-key")
    if (!key) throw new Error("Hibira: no app key. Set HIBIRA_APP_KEY and add {% hibira_scripts %} to <head>.")
    var tls = meta("hibira-tls") !== "false"
    var port = Number(meta("hibira-port") || (tls ? 443 : 80))
    client = new window.Pusher(key, {
      cluster: "hkg", // required by pusher-js, unused once wsHost is set
      wsHost: meta("hibira-host") || "ws.hibira.io",
      wsPort: port,
      wssPort: port,
      forceTLS: tls,
      enabledTransports: ["ws", "wss"],
      channelAuthorization: { customHandler: authorize },
    })
    return client
  }

  function socketId() {
    return client && client.connection ? client.connection.socket_id || null : null
  }

  function fragment(html) {
    var template = document.createElement("template")
    template.innerHTML = html || ""
    return template.content
  }

  function targetsOf(op) {
    if (op.targets) return Array.prototype.slice.call(document.querySelectorAll(op.targets))
    var el = op.target ? document.getElementById(op.target) : null
    return el ? [el] : []
  }

  function processNew(nodes) {
    nodes.forEach(function (node) {
      if (node.nodeType === 1 && window.htmx && typeof window.htmx.process === "function") window.htmx.process(node)
    })
  }

  // Inserting a row that is already in the list (the browser that made the
  // change rendered it itself) replaces it rather than adding a duplicate.
  function withoutDuplicates(container, frag) {
    Array.prototype.forEach.call(frag.children, function (child) {
      if (!child.id) return
      var existing = container.querySelector("#" + CSS.escape(child.id))
      if (existing && existing.parentElement === container) existing.remove()
    })
    return frag
  }

  function apply(op) {
    if (op.action === "refresh") return scheduleRefresh()
    targetsOf(op).forEach(function (el) {
      var before = new CustomEvent("hibira:before-swap", { bubbles: true, cancelable: true, detail: op })
      if (!el.dispatchEvent(before)) return
      var frag = op.action === "remove" ? null : fragment(op.html)
      var nodes = frag ? Array.prototype.slice.call(frag.childNodes) : []
      switch (op.action) {
        case "append": el.append(withoutDuplicates(el, frag)); break
        case "prepend": el.prepend(withoutDuplicates(el, frag)); break
        case "replace": el.replaceWith(frag); break
        case "update": el.replaceChildren(frag); break
        case "before": el.before(frag); break
        case "after": el.after(frag); break
        case "remove": el.remove(); break
        default: return
      }
      processNew(nodes)
      var target = op.action === "replace" || op.action === "remove" ? document : el
      target.dispatchEvent(new CustomEvent("hibira:swapped", { bubbles: true, detail: op }))
    })
  }

  // Refetches this page and swaps in its <body>, keeping the scroll
  // position. Several refreshes in a row become one fetch. Turbo 8 apps get
  // a Turbo morph refresh instead.
  function scheduleRefresh() {
    clearTimeout(refreshTimer)
    refreshTimer = setTimeout(refresh, 150)
  }

  function refresh() {
    if (window.Turbo && window.Turbo.session && typeof window.Turbo.session.refresh === "function") {
      return window.Turbo.session.refresh(location.href)
    }
    var x = window.scrollX
    var y = window.scrollY
    var active = document.activeElement
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA") && active.value) {
      return scheduleRefresh() // don't throw away what someone is typing
    }
    fetch(location.href, { headers: { "X-Hibira-Refresh": "1" }, credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.text() : null })
      .then(function (html) {
        if (html == null) return
        var doc = new DOMParser().parseFromString(html, "text/html")
        document.body.replaceWith(document.adoptNode(doc.body))
        window.scrollTo(x, y)
        processNew([document.body])
        document.dispatchEvent(new CustomEvent("hibira:refreshed", { bubbles: true }))
      })
      .catch(function () {})
  }

  class HibiraStreamElement extends HTMLElement {
    static get observedAttributes() { return ["channel", "signed-stream"] }

    connectedCallback() { this.subscribe() }
    disconnectedCallback() { this.unsubscribe() }

    attributeChangedCallback() {
      if (this.subscribedTo) {
        this.unsubscribe()
        this.subscribe()
      }
    }

    subscribe() {
      var name = this.getAttribute("channel")
      if (!name) return
      var stream = streams.get(name)
      if (!stream) {
        stream = { elements: new Set(), timer: null, channel: null }
        streams.set(name, stream)
      }
      stream.signed = this.getAttribute("signed-stream")
      clearTimeout(stream.timer)
      if (!stream.channel) {
        stream.channel = getClient().subscribe(name)
        stream.channel.bind(EVENT, apply)
      }
      var self = this
      this.connected = function () { self.setAttribute("connected", "") }
      stream.channel.bind("pusher:subscription_succeeded", this.connected)
      if (stream.channel.subscribed) this.connected()
      stream.elements.add(this)
      this.subscribedTo = name
    }

    unsubscribe() {
      var name = this.subscribedTo
      var stream = name && streams.get(name)
      this.subscribedTo = null
      this.removeAttribute("connected")
      if (!stream) return
      stream.channel.unbind("pusher:subscription_succeeded", this.connected)
      stream.elements.delete(this)
      if (stream.elements.size === 0) {
        clearTimeout(stream.timer)
        stream.timer = setTimeout(function () {
          if (stream.elements.size > 0) return
          stream.channel.unbind(EVENT, apply)
          if (client) client.unsubscribe(name)
          streams.delete(name)
        }, UNSUBSCRIBE_DELAY)
      }
    }
  }

  // htmx requests carry this browser's socket ID, so the server can skip it
  // (django_hibira.socket_id(request)).
  document.addEventListener("htmx:configRequest", function (event) {
    var id = socketId()
    if (id) event.detail.headers["X-Hibira-Socket-Id"] = id
  })

  if (!customElements.get("hibira-stream")) customElements.define("hibira-stream", HibiraStreamElement)

  window.Hibira = { client: getClient, socketId: socketId, apply: apply }
})()
