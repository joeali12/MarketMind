/**
 * MarketMind Stitch runtime — safe binder for the approved screens.
 * Rules: never set textContent on nodes that have children (that wiped the page).
 * Talks to /api on the same origin when served by uvicorn, or :8000 from Streamlit.
 */
(function () {
  "use strict";

  var KEY = "mm_session_id";
  var META_KEY = "mm_session_meta";
  var API =
    window.MM_API_BASE ||
    (/^850\d$/.test(String(location.port || ""))
      ? "http://127.0.0.1:8000"
      : "");

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }
  function pageName() {
    var p = (location.pathname.split("/").pop() || "").replace(/\.html$/, "");
    return p || "welcome_upload_pipeline";
  }
  function getSession() {
    return sessionStorage.getItem(KEY) || "";
  }
  function setSession(id, meta) {
    sessionStorage.setItem(KEY, id || "");
    if (meta) sessionStorage.setItem(META_KEY, JSON.stringify(meta));
  }
  function getMeta() {
    try {
      return JSON.parse(sessionStorage.getItem(META_KEY) || "{}");
    } catch (e) {
      return {};
    }
  }
  function money(n, code) {
    var v = Number(n);
    if (!Number.isFinite(v)) return "—";
    var formatted = Math.round(v).toLocaleString("en-GB");
    return (code && code !== "UNSPECIFIED" ? code + " " : "") + formatted;
  }
  function pct(n) {
    var v = Number(n);
    if (!Number.isFinite(v)) return "—";
    return (v * 100).toFixed(1) + "%";
  }
  function shortDate(s) {
    return s ? String(s).slice(0, 10) : "—";
  }
  function toast(msg, isError) {
    var el = document.getElementById("mm-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "mm-toast";
      el.setAttribute("role", "status");
      el.style.cssText =
        "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:10000;" +
        "background:#213145;color:#eaf1ff;padding:12px 18px;border-radius:999px;" +
        "font:500 14px Inter,system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.18);max-width:92vw";
      document.body.appendChild(el);
    }
    el.style.background = isError ? "#ba1a1a" : "#213145";
    el.textContent = msg;
    el.style.display = "block";
    clearTimeout(el._t);
    el._t = setTimeout(function () {
      el.style.display = "none";
    }, 4500);
  }
  async function api(path, opts) {
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, 60000);
    try {
      var res = await fetch(API + path, Object.assign({}, opts || {}, { signal: controller.signal }));
      var text = await res.text();
      var data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (e) {
        data = { detail: text };
      }
      if (!res.ok) {
        var detail = (data && (data.detail || data.message)) || res.statusText;
        if (typeof detail === "object") detail = JSON.stringify(detail);
        throw new Error(detail || "Request failed");
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }
  function go(name) {
    var base = location.pathname.replace(/[^/]+$/, "");
    location.href = base + name + ".html";
  }
  /** Only update leaf text nodes — never wipe container trees. */
  function setLeafByIncludes(includes, text, root) {
    var hit = false;
    $all("*", root || document).forEach(function (el) {
      if (el.children && el.children.length) return;
      var t = (el.textContent || "").trim();
      if (!t) return;
      if (includes.some(function (s) { return t.indexOf(s) !== -1; })) {
        el.textContent = text;
        hit = true;
      }
    });
    return hit;
  }
  function setStatNearLabel(labelRe, value) {
    $all(".font-stat-metric, [class*='stat-metric']").forEach(function (metric) {
      var card = metric.closest("div") || metric.parentElement;
      var probe = card && card.parentElement ? card.parentElement : card;
      var label = (probe && probe.textContent) || "";
      if (labelRe.test(label)) metric.textContent = value;
    });
  }
  function fillHeaderBadge(filename, currency) {
    var label = (filename || "Uploaded file") + (currency ? " · " + currency : "");
    $all("header .rounded-full span, header span").forEach(function (el) {
      if (el.children && el.children.length) return;
      var t = (el.textContent || "").trim();
      if (!t || t.length > 90) return;
      if (/Al-Madina|Q3_Sales|Boutique|\.csv|\.xlsx|Uploaded file|Retail_Test|uci_|synth_/i.test(t)) {
        el.textContent = label;
      }
    });
  }
  function hideMockDeltas(root) {
    $all("span", root || document).forEach(function (chip) {
      if (chip.children && chip.children.length) return;
      if (/^[+\-]\d+(\.\d+)?%$/.test((chip.textContent || "").trim()) ||
          /trending_up/.test(chip.textContent || "")) {
        var parent = chip.parentElement;
        if (parent && /[+\-]\d+(\.\d+)?%/.test(parent.textContent || "")) {
          parent.style.display = "none";
        }
      }
    });
  }
  function ensureLivePanel(id) {
    var existing = document.getElementById(id);
    if (existing) return existing;
    var panel = document.createElement("section");
    panel.id = id;
    panel.style.cssText =
      "max-width:1440px;margin:0 auto;padding:1rem 2rem 2.5rem;" +
      "font-family:Inter,system-ui,sans-serif;color:#0b1c30";
    var main = $("main") || document.body;
    main.appendChild(panel);
    return panel;
  }
  function wireNav() {
    var routes = {
      dashboard: function () {
        go("store_dashboard");
      },
      "upload-and-pipeline": function () {
        go("welcome_upload_pipeline");
      },
      products: function () {
        if (getSession()) go("store_dashboard");
        else toast("Upload a file first, then open Products from the store view", true);
      },
      "customers-and-groups": function () {
        if (getSession()) go("store_dashboard");
        else toast("Upload a file first to see customer groups", true);
      },
      assistant: function () {
        toast("Assistant answers from your uploaded file after analysis is ready");
      },
    };
    var active =
      pageName() === "store_dashboard"
        ? "dashboard"
        : pageName() === "welcome_upload_pipeline"
          ? "upload-and-pipeline"
          : "upload-and-pipeline";
    var activeClasses =
      ($("nav[data-active-classes]") || {}).getAttribute("data-active-classes") ||
      "bg-inverse-surface text-inverse-on-surface font-semibold shadow-sm";
    $all("nav a[data-path]").forEach(function (a) {
      var path = a.getAttribute("data-path");
      a.addEventListener("click", function (ev) {
        if (!routes[path]) return;
        ev.preventDefault();
        routes[path]();
      });
      if (path === active) {
        a.setAttribute("aria-current", "page");
        activeClasses.split(/\s+/).forEach(function (c) {
          if (c) a.classList.add(c);
        });
      }
    });
  }

  async function prepareSession(sessionId, opts) {
    opts = opts || {};
    await api("/api/upload/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        currency_code: opts.currency || "EGP",
        date_format: opts.dateFormat || "dayfirst",
        confirm_date_format: true,
      }),
    });
    var profile = await api("/api/upload/" + sessionId + "/profile");
    if (!profile.mapping_confirmed) {
      var effective = (profile.mapping && profile.mapping.effective_mapping) || {};
      if (Object.keys(effective).length) {
        await api("/api/upload/mapping", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            mapping: effective,
            confirm: true,
          }),
        });
      }
    }
    await api("/api/upload/confirm-profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, confirmed: true }),
    });
    return api("/api/upload/" + sessionId + "/profile");
  }

  async function handleUpload(file) {
    if (!file) return;
    toast("Uploading " + file.name + "…");
    var fd = new FormData();
    fd.append("file", file);
    var up = await api("/api/upload", { method: "POST", body: fd });
    var currency = up.currency_code;
    if (!currency || currency === "UNSPECIFIED") {
      currency = /uk|gbp|online.?retail/i.test(file.name) ? "GBP" : "EGP";
    }
    var dateFormat =
      (up.date_format_info && up.date_format_info.suggested) ||
      up.date_format ||
      "dayfirst";
    toast("Confirming columns & currency…");
    await prepareSession(up.session_id, { currency: currency, dateFormat: dateFormat });
    setSession(up.session_id, {
      filename: up.filename,
      row_count: up.row_count_preview,
      currency_code: currency,
      date_format: dateFormat,
    });
    go("file_understanding_setup");
  }

  function wireWelcome() {
    var input = $("#sales-file-input");
    if (input) {
      input.addEventListener("change", function () {
        var file = input.files && input.files[0];
        handleUpload(file).catch(function (e) {
          toast(String(e.message || e), true);
        });
      });
    }
    $all("button").forEach(function (btn) {
      var t = (btn.textContent || "").replace(/\s+/g, " ");
      if (/Load Cairo Fashion Demo Store|Load sample store dashboard/i.test(t)) {
        btn.onclick = function () {
          sessionStorage.removeItem(KEY);
          setSession("", { demo: true, mode: "uk_demo", filename: "UK Online Retail II sample" });
          go("store_dashboard");
        };
        var label = btn.querySelector("span:not(.material-symbols-outlined)") || btn;
        if (label && /Load Cairo|Load sample/.test(label.textContent || "")) {
          label.textContent = "Load sample store dashboard";
        }
      }
    });
  }

  async function renderFileUnderstanding() {
    var sid = getSession();
    if (!sid) {
      toast("Upload a sales file first", true);
      go("welcome_upload_pipeline");
      return;
    }
    var profile = await api("/api/upload/" + sid + "/profile");
    var meta = getMeta();
    var currency =
      (profile.currency && profile.currency.code) || meta.currency_code || "EGP";
    var rows = profile.row_count || 0;
    var cols = profile.column_count || 0;
    var structure = profile.structure || {};
    fillHeaderBadge(meta.filename || "upload", currency);

    // Leaf-only title / status updates
    setLeafByIncludes(["File Profile:"], "File Profile: " + (meta.filename || "upload"));
    setLeafByIncludes(
      ["File parsed successfully"],
      "File parsed successfully · " +
        rows.toLocaleString("en-GB") +
        " rows · " +
        cols +
        " detected columns"
    );
    setStatNearLabel(/Validated Rows/i, rows.toLocaleString("en-GB"));
    setStatNearLabel(
      /Covered Date Span/i,
      shortDate(structure.date_min) + " – " + shortDate(structure.date_max)
    );
    setStatNearLabel(/Detected Customers/i, String(structure.unique_customers || 0));
    setStatNearLabel(/Gross Ledger|Ledger Value/i, money(structure.eligible_spend, currency));

    // Live summary panel (additive, does not remove Stitch layout)
    var panel = ensureLivePanel("mm-live-file");
    var mappings = (profile.column_mappings && profile.column_mappings.mappings) || [];
    var preview = profile.preview_rows || [];
    var mapRows = mappings
      .slice(0, 12)
      .map(function (m) {
        return (
          "<tr><td style='padding:8px 0;border-bottom:1px solid #e7e5f2'>" +
          (m.target || "") +
          "</td><td style='padding:8px 0;border-bottom:1px solid #e7e5f2'>" +
          (m.source_column || "") +
          "</td><td style='padding:8px 0;border-bottom:1px solid #e7e5f2;text-align:end'>" +
          Math.round((m.confidence || 0) * 100) +
          "%</td></tr>"
        );
      })
      .join("");
    var previewKeys = preview.length ? Object.keys(preview[0]).slice(0, 6) : [];
    var previewRows = preview
      .slice(0, 5)
      .map(function (row) {
        return (
          "<tr>" +
          previewKeys
            .map(function (k) {
              return (
                "<td style='padding:6px 8px 6px 0;border-bottom:1px solid #e7e5f2;font-size:12px'>" +
                String(row[k] == null ? "" : row[k]).slice(0, 48) +
                "</td>"
              );
            })
            .join("") +
          "</tr>"
        );
      })
      .join("");

    panel.innerHTML =
      '<div style="display:grid;gap:12px;grid-template-columns:1.2fr .8fr">' +
      '<article style="background:#fff;border:1px solid #c7c4d8;border-radius:22px;padding:16px 18px">' +
      "<h2 style='margin:0 0 8px;font:600 18px Inter,sans-serif'>Detected column mapping</h2>" +
      "<table style='width:100%;border-collapse:collapse;font:13px Inter,sans-serif'><thead><tr>" +
      "<th style='text-align:start'>MarketMind</th><th style='text-align:start'>Your header</th><th style='text-align:end'>Confidence</th>" +
      "</tr></thead><tbody>" +
      (mapRows || "<tr><td colspan='3'>Mapping ready</td></tr>") +
      "</tbody></table></article>" +
      '<article style="background:#fff;border:1px solid #c7c4d8;border-radius:22px;padding:16px 18px">' +
      "<h2 style='margin:0 0 8px;font:600 18px Inter,sans-serif'>Confirm before cleaning</h2>" +
      "<p style='margin:0 0 10px;color:#464555;font:14px Inter,sans-serif'>Currency: <strong>" +
      currency +
      "</strong> · Dates: <strong>" +
      (meta.date_format || "dayfirst") +
      "</strong></p>" +
      "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px'>" +
      ["EGP", "SAR", "AED", "USD", "GBP"]
        .map(function (c) {
          var on = c === currency;
          return (
            '<button type="button" data-mm-currency="' +
            c +
            '" style="border:0;border-radius:999px;padding:8px 14px;cursor:pointer;' +
            (on
              ? "background:#213145;color:#fff"
              : "background:#eff4ff;color:#464555") +
            '">' +
            c +
            "</button>"
          );
        })
        .join("") +
      "</div>" +
      '<button type="button" id="mm-next-cleaning" style="width:100%;border:0;border-radius:999px;padding:12px 16px;background:#3525cd;color:#fff;font:600 14px Inter,sans-serif;cursor:pointer">Next: Review data cleaning →</button>' +
      '<button type="button" id="mm-reupload" style="width:100%;margin-top:8px;border:0;border-radius:999px;padding:12px 16px;background:#eff4ff;color:#0b1c30;font:500 14px Inter,sans-serif;cursor:pointer">Re-upload different file</button>' +
      "</article></div>" +
      (previewRows
        ? '<article style="margin-top:12px;background:#fff;border:1px solid #c7c4d8;border-radius:22px;padding:16px 18px;overflow:auto">' +
          "<h2 style='margin:0 0 8px;font:600 18px Inter,sans-serif'>Parsed sample rows</h2>" +
          "<table style='width:100%;border-collapse:collapse'><thead><tr>" +
          previewKeys
            .map(function (k) {
              return "<th style='text-align:start;font:600 12px Inter,sans-serif;color:#464555'>" + k + "</th>";
            })
            .join("") +
          "</tr></thead><tbody>" +
          previewRows +
          "</tbody></table></article>"
        : "");

    $all("[data-mm-currency]", panel).forEach(function (btn) {
      btn.onclick = async function () {
        var code = btn.getAttribute("data-mm-currency");
        try {
          await api("/api/upload/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sid, currency_code: code }),
          });
          var m = getMeta();
          m.currency_code = code;
          setSession(sid, m);
          toast("Currency set to " + code);
          await renderFileUnderstanding();
        } catch (e) {
          toast(String(e.message || e), true);
        }
      };
    });
    var next = $("#mm-next-cleaning");
    if (next) next.onclick = function () { go("data_cleaning_review"); };
    var re = $("#mm-reupload");
    if (re)
      re.onclick = function () {
        sessionStorage.removeItem(KEY);
        go("welcome_upload_pipeline");
      };

    // Also wire original Stitch footer buttons if present
    $all("button").forEach(function (btn) {
      var t = (btn.textContent || "").replace(/\s+/g, " ");
      if (/Next: Review data cleaning/i.test(t) && btn.id !== "mm-next-cleaning") {
        btn.onclick = function () { go("data_cleaning_review"); };
      }
      if (/Re-upload different file/i.test(t) && btn.id !== "mm-reupload") {
        btn.onclick = function () {
          sessionStorage.removeItem(KEY);
          go("welcome_upload_pipeline");
        };
      }
    });
  }

  async function renderCleaning() {
    var sid = getSession();
    if (!sid) {
      toast("Upload a sales file first", true);
      go("welcome_upload_pipeline");
      return;
    }
    var data = await api(
      "/api/upload/cleaning-proposals?session_id=" + encodeURIComponent(sid),
      { method: "POST" }
    );
    var meta = getMeta();
    var currency = data.currency_code || meta.currency_code || "EGP";
    var baseline = data.baseline || {};
    var proposals = data.proposals || [];
    fillHeaderBadge(meta.filename, currency);
    setLeafByIncludes(["Data Quality"], "Data Quality & Cleaning Review");

    var panel = ensureLivePanel("mm-live-cleaning");
    panel.innerHTML =
      '<article style="background:#fff;border:1px solid #c7c4d8;border-radius:22px;padding:16px 18px;margin-bottom:12px">' +
      "<p style='margin:0;color:#464555;font:14px Inter,sans-serif'>" +
      (baseline.rows || 0).toLocaleString("en-GB") +
      " rows from <strong>" +
      (meta.filename || "your upload") +
      "</strong>. Eligible spend baseline: <strong>" +
      money(baseline.eligible_spend, currency) +
      "</strong>.</p></article>" +
      proposals
        .map(function (p) {
          return (
            '<article style="background:#fff;border:1px solid #c7c4d8;border-radius:22px;padding:16px 18px;margin-bottom:10px">' +
            "<h3 style='margin:0 0 6px;font:600 16px Inter,sans-serif'>" +
            (p.title_en || p.id) +
            "</h3>" +
            "<p style='margin:0;color:#464555;font:14px/1.5 Inter,sans-serif'>" +
            (p.reason_en || "") +
            "</p>" +
            "<p style='margin:8px 0 0;color:#777587;font:12px Inter,sans-serif'>Rows: " +
            (p.rows_affected || 0) +
            (p.default_accepted ? " · suggested: apply" : " · suggested: review") +
            "</p></article>"
          );
        })
        .join("") +
      '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:12px">' +
      '<button type="button" id="mm-export-clean" style="border:0;border-radius:999px;padding:12px 18px;background:#eff4ff;cursor:pointer;font:500 14px Inter,sans-serif">Export cleaned CSV</button>' +
      '<button type="button" id="mm-open-dash" style="border:0;border-radius:999px;padding:12px 18px;background:#3525cd;color:#fff;cursor:pointer;font:600 14px Inter,sans-serif">Finish cleaning & open dashboard</button>' +
      "</div>";

    $("#mm-open-dash").onclick = function () { go("store_dashboard"); };
    $("#mm-export-clean").onclick = async function () {
      try {
        var accepted = proposals.filter(function (p) { return p.default_accepted; }).map(function (p) { return p.id; });
        var res = await fetch(API + "/api/upload/apply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sid, accepted_ids: accepted }),
        });
        if (!res.ok) throw new Error(await res.text());
        var blob = await res.blob();
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "marketmind_cleaned.csv";
        a.click();
        toast("Cleaned CSV downloaded");
      } catch (e) {
        toast(String(e.message || e), true);
      }
    };

    $all("button").forEach(function (btn) {
      var t = (btn.textContent || "").replace(/\s+/g, " ");
      if (/Finish Cleaning|Open My Dashboard/i.test(t) && btn.id !== "mm-open-dash") {
        btn.onclick = function () { go("store_dashboard"); };
      }
    });
  }

  function drawTrend(host, trend) {
    if (!host || !trend || trend.length < 2) return;
    var values = trend.map(function (r) { return Number(r.spend || r.spend_gbp || 0); });
    var peak = Math.max.apply(null, values.concat([1]));
    var w = 640;
    var h = 160;
    var step = w / (values.length - 1);
    var pts = values
      .map(function (v, i) {
        return (i * step).toFixed(1) + "," + (h - (v / peak) * (h - 16) - 8).toFixed(1);
      })
      .join(" ");
    var area = "0," + h + " " + pts + " " + w + "," + h;
    host.innerHTML =
      '<svg viewBox="0 0 ' + w + " " + h + '" width="100%" height="160" role="img">' +
      '<polygon points="' + area + '" fill="#4f46e5" opacity="0.16"></polygon>' +
      '<polyline points="' + pts + '" fill="none" stroke="#4f46e5" stroke-width="3"></polyline></svg>';
  }

  async function renderStore() {
    var sid = getSession();
    var meta = getMeta();
    var overview;
    var productsPayload = { products: [] };
    if (sid) {
      overview = await api("/api/upload/" + sid + "/overview");
      try {
        productsPayload = await api("/api/upload/" + sid + "/products");
      } catch (e) {
        productsPayload = { products: [] };
      }
    } else {
      overview = await api("/api/overview");
      try {
        productsPayload = await api("/api/products");
      } catch (e) {
        productsPayload = { products: [] };
      }
      meta = {
        filename: overview.provenance || "UK Online Retail II sample",
        demo: true,
        currency_code: overview.currency || "GBP",
      };
    }
    var m = overview.metrics || {};
    var currency =
      overview.currency_label ||
      overview.currency_code ||
      overview.currency ||
      meta.currency_code ||
      "GBP";
    var filename = overview.filename || meta.filename || "Store";
    fillHeaderBadge(filename, currency);
    hideMockDeltas(document);

    var sales = m.sales != null ? m.sales : m.sales_gbp;
    var orders = m.orders;
    var customers = m.customers;
    var aov = m.average_order_value != null ? m.average_order_value : m.average_order_value_gbp;
    var returning = m.returning_customer_share;

    setLeafByIncludes(["Al-Madina Boutique"], filename);
    setStatNearLabel(/Eligible Net Spend|Eligible sales/i, money(sales, currency));
    setStatNearLabel(/Completed Orders|^Orders$/i, orders == null ? "—" : Number(orders).toLocaleString("en-GB"));
    setStatNearLabel(/Identified Shoppers|Customers/i, customers == null ? "—" : Number(customers).toLocaleString("en-GB"));
    setStatNearLabel(/Average Basket|AOV/i, aov == null ? "—" : money(aov, currency));
    setStatNearLabel(/Repeat Customer|Returning/i, returning == null ? "—" : pct(returning));
    setLeafByIncludes(["Jul 1", "Last 90 Days", "Sep 30"], shortDate(m.date_min) + " – " + shortDate(m.date_max));

    var products = productsPayload.products || [];
    var insights = overview.evidence_insights || overview.insights || [];
    var trend = overview.monthly_trend || [];
    var panel = ensureLivePanel("mm-live-store");
    panel.innerHTML =
      '<div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:12px">' +
      [
        ["Eligible sales", money(sales, currency)],
        ["Orders", orders == null ? "—" : Number(orders).toLocaleString("en-GB")],
        ["Customers", customers == null ? "—" : Number(customers).toLocaleString("en-GB")],
        ["AOV", aov == null ? "—" : money(aov, currency)],
        ["Returning", returning == null ? "—" : pct(returning)],
      ]
        .map(function (pair) {
          return (
            '<article style="background:#fff;border:1px solid #c7c4d8;border-radius:18px;padding:14px">' +
            "<div style='color:#464555;font:12px Inter,sans-serif'>" +
            pair[0] +
            "</div><div style='margin-top:6px;font:700 22px Inter,sans-serif'>" +
            pair[1] +
            "</div></article>"
          );
        })
        .join("") +
      "</div>" +
      '<div style="display:grid;grid-template-columns:1.4fr .8fr;gap:12px">' +
      '<article style="background:#fff;border:1px solid #c7c4d8;border-radius:22px;padding:16px">' +
      "<h2 style='margin:0 0 8px;font:600 18px Inter,sans-serif'>Monthly eligible spend</h2>" +
      '<div id="mm-trend-host"></div></article>' +
      '<article style="background:#fff;border:1px solid #c7c4d8;border-radius:22px;padding:16px">' +
      "<h2 style='margin:0 0 8px;font:600 18px Inter,sans-serif'>Evidence</h2>" +
      "<ul style='margin:0;padding-inline-start:1.1rem;color:#464555;font:13px/1.5 Inter,sans-serif'>" +
      (insights.length
        ? insights
            .slice(0, 4)
            .map(function (ins) {
              return "<li>" + (ins.title_en || ins.claim || "") + "</li>";
            })
            .join("")
        : "<li>" + (overview.caveat_en || "Descriptive totals from this file only.") + "</li>") +
      "</ul></article></div>" +
      '<article style="margin-top:12px;background:#fff;border:1px solid #c7c4d8;border-radius:22px;padding:16px">' +
      "<h2 style='margin:0 0 8px;font:600 18px Inter,sans-serif'>Top products</h2>" +
      "<table style='width:100%;border-collapse:collapse;font:13px Inter,sans-serif'><tbody>" +
      products
        .slice(0, 8)
        .map(function (p) {
          return (
            "<tr><td style='padding:8px 0;border-bottom:1px solid #e7e5f2'>" +
            (p.description || p.stock_code || "") +
            "</td><td style='padding:8px 0;border-bottom:1px solid #e7e5f2;text-align:end'>" +
            money(p.spend != null ? p.spend : p.spend_gbp, currency) +
            "</td><td style='padding:8px 0;border-bottom:1px solid #e7e5f2;text-align:end'>" +
            Number(p.quantity || 0).toLocaleString("en-GB") +
            "</td></tr>"
          );
        })
        .join("") +
      "</tbody></table>" +
      "<p style='margin:10px 0 0;color:#777587;font:12px Inter,sans-serif'>" +
      (overview.caveat_en || "") +
      "</p></article>";

    drawTrend($("#mm-trend-host"), trend);

    // Ask Assistant button → grounded Q&A if session exists
    $all("button").forEach(function (btn) {
      var t = (btn.textContent || "").replace(/\s+/g, " ");
      if (/Ask Assistant/i.test(t)) {
        btn.onclick = async function () {
          if (!sid) {
            toast("Upload your own file to ask about it", true);
            return;
          }
          var q = window.prompt("Ask about this upload (grounded answers only):", "What is total eligible spend?");
          if (!q) return;
          try {
            var ans = await api("/api/upload/assistant", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ session_id: sid, question: q, lang: "en" }),
            });
            toast((ans.answer || ans.message || JSON.stringify(ans)).slice(0, 220));
          } catch (e) {
            toast(String(e.message || e), true);
          }
        };
      }
    });
  }

  async function boot() {
    wireNav();
    var page = pageName();
    try {
      if (page === "welcome_upload_pipeline") wireWelcome();
      else if (page === "file_understanding_setup") await renderFileUnderstanding();
      else if (page === "data_cleaning_review") await renderCleaning();
      else if (page === "store_dashboard") await renderStore();
    } catch (e) {
      console.error(e);
      toast(String(e.message || e), true);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
