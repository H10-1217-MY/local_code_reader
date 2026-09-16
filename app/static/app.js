let lastResult = null;
let lastFile = null;
let chatHistory = [];
let projectFiles = [];
let projectSkipped = [];
let projectExcluded = [];
let lastProjectResult = null;
let lastProjectDocs = null;
let projectChatHistory = [];
let appStatus = null;
let setupFiles = [];
let lastSetupResult = null;

const byId = (id) => document.getElementById(id);
const EXCLUDED_DIRS = new Set([".git", ".venv", "venv", "env", "node_modules", "__pycache__", "build", "dist", ".idea", ".vscode", ".mypy_cache", ".pytest_cache", ".ruff_cache"]);

function showError(message) {
  byId("errorBox").textContent = message;
  byId("errorBox").classList.remove("hidden");
}
function clearError() { byId("errorBox").classList.add("hidden"); byId("errorBox").textContent = ""; }
function setLoading(text) { byId("loadingBox").textContent = text; byId("loadingBox").classList.remove("hidden"); }
function clearLoading() { byId("loadingBox").classList.add("hidden"); }

function fillList(id, values, {stripLeadingNumber = false} = {}) {
  const el = byId(id); el.innerHTML = "";
  const items = values && values.length ? values : ["特記事項なし"];
  items.forEach(value => {
    const li = document.createElement("li");
    let text = String(value);
    if (stripLeadingNumber) text = text.replace(/^\s*(?:\d+[.．)、:]|[①-⑳]|[（(]\d+[）)])\s*/, "");
    li.textContent = text; el.appendChild(li);
  });
}
function lineRange(symbol) {
  if (!symbol || !symbol.line) return "行番号不明";
  return symbol.end_line && symbol.end_line !== symbol.line ? `L${symbol.line}–L${symbol.end_line}` : `L${symbol.line}`;
}
function createBadge(text, type) { const span = document.createElement("span"); span.className = `badge ${type}`; span.textContent = text; return span; }
function findStaticSymbol(staticValues, llmName) {
  if (!staticValues || !llmName) return null;
  return staticValues.find(v => v.name === llmName || v.qualified_name === llmName || (v.qualified_name && v.qualified_name.endsWith(`.${llmName}`))) || null;
}
function renderStaticSymbols(id, values, kind) {
  const el = byId(id); el.innerHTML = "";
  if (!values || !values.length) { el.textContent = "検出なし"; return; }
  values.forEach(v => {
    const box = document.createElement("div"); box.className = "symbol";
    const head = document.createElement("div"); head.className = "symbol-head";
    const name = document.createElement("strong"); name.textContent = v.qualified_name || v.name; head.append(name, createBadge(lineRange(v), "fact")); box.appendChild(head);
    if (kind === "function") {
      const details = []; if (v.async) details.push("async"); if (v.kind === "method") details.push("method"); if (v.args?.length) details.push(`args: ${v.args.join(", ")}`);
      if (details.length) { const p = document.createElement("p"); p.className = "symbol-meta"; p.textContent = details.join(" / "); box.appendChild(p); }
      if (v.calls?.length) { const p = document.createElement("p"); p.className = "symbol-meta"; p.textContent = `主な呼び出し: ${v.calls.slice(0, 8).join(", ")}${v.calls.length > 8 ? " …" : ""}`; box.appendChild(p); }
    } else if (v.bases?.length) { const p = document.createElement("p"); p.className = "symbol-meta"; p.textContent = `継承: ${v.bases.join(", ")}`; box.appendChild(p); }
    el.appendChild(box);
  });
}
function renderInterpretedSymbols(id, llmValues, staticValues) {
  const el = byId(id); el.innerHTML = "";
  if (!llmValues?.length) { el.textContent = "特記事項なし"; return; }
  llmValues.forEach(v => {
    const fact = findStaticSymbol(staticValues, v.name); const box = document.createElement("div"); box.className = "symbol";
    const head = document.createElement("div"); head.className = "symbol-head"; const name = document.createElement("strong"); name.textContent = fact?.qualified_name || v.name; head.appendChild(name); head.appendChild(fact ? createBadge(lineRange(fact), "fact") : createBadge("静的解析で未照合", "warning")); box.appendChild(head);
    const role = document.createElement("p"); role.className = "symbol-role"; role.append(createBadge("LLM解釈", "interpretation"), document.createTextNode(` ${v.role}`)); box.appendChild(role); el.appendChild(box);
  });
}
function renderBasicFacts(data) {
  const el = byId("basicFacts"); el.innerHTML = "";
  [["言語", data.file.language], ["行数", `${data.file.line_count} lines`], ["文字数", `${data.file.char_count} chars`], ["関数・メソッド", `${data.static_analysis.functions?.length || 0}`], ["クラス", `${data.static_analysis.classes?.length || 0}`]].forEach(([label, value]) => {
    const dt = document.createElement("dt"); dt.textContent = label; const dd = document.createElement("dd"); dd.textContent = value; el.append(dt, dd);
  });
}
function resetChat() {
  chatHistory = []; if (lastResult) lastResult.qa_history = [];
  byId("chatMessages").innerHTML = '<div class="chat-empty">解析結果を見て気になったところを、そのまま質問できます。</div>'; byId("askStatus").textContent = "";
}
function renderSingleResult(data) {
  lastResult = data; lastResult.qa_history = lastResult.qa_history || []; resetChat();
  byId("fileTitle").textContent = data.file.name; byId("fileMeta").textContent = `${data.file.language} / ${data.file.line_count} lines / model: ${data.model}`;
  renderBasicFacts(data); fillList("staticImports", data.static_analysis.imports); fillList("staticDependencies", data.static_analysis.detected_external_dependencies); fillList("staticReferences", data.static_analysis.references); renderStaticSymbols("staticFunctions", data.static_analysis.functions, "function"); renderStaticSymbols("staticClasses", data.static_analysis.classes, "class");
  byId("purpose").textContent = data.analysis.purpose || ""; byId("overview").textContent = data.analysis.overview || ""; fillList("mainFlow", data.analysis.main_flow, {stripLeadingNumber: true}); fillList("changeRisks", data.analysis.change_risks);
  renderInterpretedSymbols("keyFunctions", data.analysis.key_functions, data.static_analysis.functions); renderInterpretedSymbols("keyClasses", data.analysis.key_classes, data.static_analysis.classes);
  fillList("inputs", data.analysis.inputs); fillList("outputs", data.analysis.outputs); fillList("unknowns", data.analysis.unknowns);
  byId("staticJson").textContent = JSON.stringify(data.static_analysis, null, 2); byId("singleResultArea").classList.remove("hidden"); byId("projectResultArea").classList.add("hidden"); byId("setupResultArea").classList.add("hidden");
}

function appendChatMessage(role, text, model = "") {
  const messages = byId("chatMessages"); messages.querySelector(".chat-empty")?.remove();
  const box = document.createElement("div"); box.className = `chat-message ${role}`; const label = document.createElement("div"); label.className = "chat-label"; label.textContent = role === "user" ? "YOU" : `OLLAMA${model ? ` / ${model}` : ""}`; const body = document.createElement("div"); body.className = "chat-body"; body.textContent = text; box.append(label, body); messages.appendChild(box); messages.scrollTop = messages.scrollHeight;
}

function resetProjectChat() {
  projectChatHistory = [];
  if (lastProjectResult) lastProjectResult.project_qa_history = [];
  byId("projectChatMessages").innerHTML = '<div class="chat-empty">解析済みプロジェクトについて、横断的に質問できます。</div>';
  byId("projectAskStatus").textContent = "";
  if (lastProjectResult) byId("projectJson").textContent = JSON.stringify(lastProjectResult, null, 2);
}
function appendProjectChatMessage(role, text, model = "", details = null) {
  const messages = byId("projectChatMessages"); messages.querySelector(".chat-empty")?.remove();
  const box = document.createElement("div"); box.className = `chat-message ${role}`;
  const label = document.createElement("div"); label.className = "chat-label"; label.textContent = role === "user" ? "YOU" : `OLLAMA${model ? ` / ${model}` : ""}`;
  const body = document.createElement("div"); body.className = "chat-body"; body.textContent = text; box.append(label, body);
  if (details && role === "assistant") {
    const meta = document.createElement("div"); meta.className = "project-qa-evidence";
    const confidence = document.createElement("p"); confidence.className = "muted mini"; confidence.textContent = `confidence: ${details.confidence || "unknown"}`; meta.appendChild(confidence);
    if (details.context_selection) {
      const route = document.createElement("p"); route.className = "muted mini";
      const selected = details.context_selection.selected_files || [];
      const factCount = details.grounding?.selected_fact_count ?? details.fact_ids?.length ?? 0;
      const semanticInfo = details.grounding?.semantic_grounding || {};
      const semanticCount = (semanticInfo.accepted_interpretation_count ?? 0) + ((semanticInfo.accepted_summary_support_fact_ids?.length || 0) ? 1 : 0);
      route.textContent = `intent: ${details.context_selection.intent_label || details.context_selection.intent || "unknown"} / selected: ${selected.length} files / history: ${details.context_selection.history_turns_used || 0} turns / grounded facts: ${factCount} / supported AI notes: ${semanticCount}`;
      meta.appendChild(route);
      if (selected.length) {
        const title = document.createElement("strong"); title.textContent = "今回参照したファイル"; meta.appendChild(title);
        const ul = document.createElement("ul"); selected.forEach(path => { const li=document.createElement("li"); li.textContent=path; ul.appendChild(li); }); meta.appendChild(ul);
      }
    }
    if (details.evidence?.length) {
      const title = document.createElement("strong"); title.textContent = "確認根拠"; meta.appendChild(title);
      const ul = document.createElement("ul"); details.evidence.forEach(ev => { const li=document.createElement("li"); const symbol=ev.symbol ? ` / ${ev.symbol}` : ""; li.textContent=`${ev.path}${symbol}: ${ev.reason || ""}`; ul.appendChild(li); }); meta.appendChild(ul);
    }
    if (details.limitations?.length) { const title=document.createElement("strong"); title.textContent="この回答の限界"; meta.appendChild(title); const ul=document.createElement("ul"); details.limitations.forEach(x=>{const li=document.createElement("li");li.textContent=x;ul.appendChild(li);});meta.appendChild(ul); }
    box.appendChild(meta);
  }
  messages.appendChild(box); messages.scrollTop = messages.scrollHeight;
}
async function fileToBase64(file) { const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ""; const chunk = 0x8000; for (let i=0;i<bytes.length;i+=chunk) binary += String.fromCharCode(...bytes.subarray(i, i+chunk)); return btoa(binary); }

function switchMode(mode) {
  const single = mode === "single";
  const project = mode === "project";
  const setup = mode === "setup";
  byId("singleMode").classList.toggle("hidden", !single);
  byId("projectMode").classList.toggle("hidden", !project);
  byId("setupMode").classList.toggle("hidden", !setup);
  byId("singleTab").classList.toggle("active", single);
  byId("projectTab").classList.toggle("active", project);
  byId("setupTab").classList.toggle("active", setup);
  byId("modelField").classList.toggle("hidden", setup);
  clearError(); clearLoading();
}
byId("singleTab").addEventListener("click", () => switchMode("single"));
byId("projectTab").addEventListener("click", () => switchMode("project"));
byId("setupTab").addEventListener("click", () => switchMode("setup"));

async function loadStatus() {
  try {
    const res = await fetch("/api/status"); const data = await res.json(); appStatus = data;
    const status = byId("status"); status.textContent = data.ollama_connected ? `Ollama接続済み / ${data.models.length} models` : "Ollama未接続 / 環境構築は利用可"; status.className = `status ${data.ollama_connected ? "ok" : "ng"}`;
    const list = byId("modelsList"); list.innerHTML = ""; data.models.forEach(model => { const option = document.createElement("option"); option.value = typeof model === "string" ? model : (model.name || model.model); list.appendChild(option); });
  } catch { byId("status").textContent = "状態確認失敗"; byId("status").className = "status ng"; }
}

byId("analyzeForm").addEventListener("submit", async (event) => {
  event.preventDefault(); clearError(); const file = byId("fileInput").files[0]; if (!file) return;
  lastFile = file; byId("analyzeButton").disabled = true; setLoading("解析中… 静的解析 → Ollama の順で処理しています。");
  try {
    const params = new URLSearchParams({filename: file.name, model: byId("modelInput").value.trim()}); const res = await fetch(`/api/analyze?${params}`, {method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: file}); const data = await res.json(); if (!res.ok) throw new Error(data.detail || "解析に失敗しました"); renderSingleResult(data);
  } catch (error) { showError(error.message); } finally { byId("analyzeButton").disabled = false; clearLoading(); }
});

byId("askForm").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!lastResult || !lastFile) return; const question = byId("questionInput").value.trim(); if (!question) return;
  const historyForRequest = chatHistory.slice(-8); appendChatMessage("user", question); byId("questionInput").value = ""; byId("askButton").disabled = true; byId("questionInput").disabled = true; byId("askStatus").textContent = "Ollamaがコードを確認中…";
  try {
    const sourceBase64 = await fileToBase64(lastFile); const res = await fetch("/api/ask", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({filename: lastResult.file.name, model: byId("modelInput").value.trim(), question, source_base64: sourceBase64, history: historyForRequest})}); const data = await res.json(); if (!res.ok) throw new Error(data.detail || "質問への回答に失敗しました"); appendChatMessage("assistant", data.answer, data.model); chatHistory.push({role:"user", content:question}, {role:"assistant", content:data.answer}); chatHistory = chatHistory.slice(-8); lastResult.qa_history.push({question, answer:data.answer, model:data.model, metrics:data.metrics}); byId("askStatus").textContent = "";
  } catch (error) { appendChatMessage("assistant", `エラー: ${error.message}`); byId("askStatus").textContent = "回答に失敗しました。"; } finally { byId("askButton").disabled = false; byId("questionInput").disabled = false; byId("questionInput").focus(); }
});
byId("clearChatButton").addEventListener("click", resetChat);
document.querySelectorAll(".quick-question").forEach(button => button.addEventListener("click", () => { byId("questionInput").value = button.dataset.question || ""; byId("questionInput").focus(); }));
byId("downloadButton").addEventListener("click", () => downloadJson(lastResult, `${lastResult?.file?.name || "analysis"}.analysis.json`));

function normalizedRelativePath(file) {
  const rel = (file.webkitRelativePath || file.name).replaceAll("\\", "/"); const parts = rel.split("/"); return parts.length > 1 ? parts.slice(1).join("/") : rel;
}
function projectNameFromFiles(files) { const rel = files[0]?.webkitRelativePath || "project"; return rel.includes("/") ? rel.split("/")[0] : "project"; }
function isAllowedByType(file) {
  if (!appStatus) return true;
  const name = file.name;
  if (appStatus.allowed_filenames?.includes(name)) return true;
  const dot = name.lastIndexOf("."); const suffix = dot >= 0 ? name.slice(dot).toLowerCase() : "";
  return appStatus.allowed_extensions?.includes(suffix);
}
function classifyProjectFile(file) {
  const rel = file.webkitRelativePath || file.name; const parts = rel.replaceAll("\\", "/").split("/");
  if (parts.some(part => EXCLUDED_DIRS.has(part))) return {mode:"exclude", reason:"除外ディレクトリ内"};
  const name = file.name; const lower = name.toLowerCase();
  if (appStatus?.project_filter?.excluded_filenames?.includes(name)) return {mode:"exclude", reason:"OS/保持用の補助ファイル"};
  if (lower.endsWith(".min.js") || lower.endsWith(".min.css")) return {mode:"exclude", reason:"minify済み生成物"};
  if (!isAllowedByType(file)) return {mode:"exclude", reason:"未対応のファイル形式"};
  const maxBytes = appStatus?.limits?.max_file_bytes || 2*1024*1024;
  if (file.size > maxBytes) return {mode:"exclude", reason:`1ファイル上限 ${(maxBytes/1024).toFixed(0)} KiB 超過`};
  if (file.size === 0) return {mode:"skip", reason:"空ファイル"};
  if (name === "__init__.py") return {mode:"structure", reason:"パッケージ初期化ファイル。内容に応じてサーバー側で再判定"};
  const structureNames = appStatus?.project_filter?.structure_only_filenames || [];
  if (structureNames.includes(name) || /^requirements(?:[-_.][\w.-]+)?\.txt$/i.test(name)) return {mode:"structure", reason:"依存・設定メタデータ"};
  return {mode:"llm", reason:"Ollama個別解析"};
}
function classifiedProjectFiles() {
  return Array.from(byId("folderInput").files).map(file => ({file, ...classifyProjectFile(file)}));
}
function renderFolderPreview() {
  const all = Array.from(byId("folderInput").files); const preview = byId("folderPreview"); preview.innerHTML = "";
  if (!all.length) { preview.textContent = "フォルダ未選択"; return; }
  const classified = classifiedProjectFiles(); const counts = {llm:0, structure:0, skip:0, exclude:0};
  classified.forEach(item => counts[item.mode]++);
  const processable = classified.filter(item => item.mode === "llm" || item.mode === "structure");
  const totalBytes = processable.reduce((sum, item) => sum + item.file.size, 0); const maxFiles = appStatus?.limits?.max_project_files || 40;
  const title = document.createElement("strong"); title.textContent = `${projectNameFromFiles(all)} / ${all.length} files 選択`;
  const badges = document.createElement("div"); badges.className = "filter-counts";
  [["LLM解析",counts.llm,"llm"],["構造のみ",counts.structure,"structure"],["スキップ",counts.skip,"skip"],["除外",counts.exclude,"exclude"]].forEach(([label,count,type]) => {
    const chip=document.createElement("span"); chip.className=`filter-chip ${type}`; chip.textContent=`${label} ${count}`; badges.appendChild(chip);
  });
  const meta=document.createElement("span"); meta.className="preview-meta"; meta.textContent=`解析対象 ${processable.length} files / ${(totalBytes/1024).toFixed(1)} KiB / 上限 ${maxFiles}`;
  preview.append(title,badges,meta);
}

byId("folderInput").addEventListener("change", renderFolderPreview);

function classifiedSetupFiles() {
  return Array.from(byId("setupFolderInput").files).map(file => {
    const base = classifyProjectFile(file);
    if (base.mode === "llm") return {file, mode:"static", reason:"環境構築モードではOllamaを呼ばず静的解析"};
    return {file, ...base};
  });
}
function renderSetupFolderPreview() {
  const all = Array.from(byId("setupFolderInput").files); const preview = byId("setupFolderPreview"); preview.innerHTML = "";
  if (!all.length) { preview.textContent = "フォルダ未選択"; return; }
  const classified = classifiedSetupFiles(); const counts = {static:0, structure:0, skip:0, exclude:0};
  classified.forEach(item => counts[item.mode] = (counts[item.mode] || 0) + 1);
  const processable = classified.filter(item => item.mode === "static" || item.mode === "structure");
  const totalBytes = processable.reduce((sum, item) => sum + item.file.size, 0); const maxFiles = appStatus?.limits?.max_environment_files || 200;
  const title = document.createElement("strong"); title.textContent = `${projectNameFromFiles(all)} / ${all.length} files 選択`;
  const badges = document.createElement("div"); badges.className = "filter-counts";
  [["静的解析",counts.static,"llm"],["依存/設定",counts.structure,"structure"],["スキップ",counts.skip,"skip"],["除外",counts.exclude,"exclude"]].forEach(([label,count,type]) => {
    const chip=document.createElement("span"); chip.className=`filter-chip ${type}`; chip.textContent=`${label} ${count}`; badges.appendChild(chip);
  });
  const meta=document.createElement("span"); meta.className="preview-meta"; meta.textContent=`環境スキャン対象 ${processable.length} files / ${(totalBytes/1024).toFixed(1)} KiB / 上限 ${maxFiles} / Ollamaなし`;
  preview.append(title,badges,meta);
}
byId("setupFolderInput").addEventListener("change", renderSetupFolderPreview);

function renderSetupResult(data) {
  lastSetupResult = data;
  byId("setupTitle").textContent = `${data.project?.name || "project"} / Environment Setup`;
  byId("setupMeta").textContent = `${data.project?.file_count || 0} files / ${data.target?.os_label || data.target?.os || "OS不明"} / shell: ${data.target?.shell || "auto"} / Ollama call: ${data.generation?.extra_ollama_call ? "yes" : "no"}`;

  const targetFacts = byId("setupTargetFacts"); targetFacts.innerHTML = "";
  [["OS", data.target?.os_label || data.target?.os], ["Shell", data.target?.shell], ["Python指定", data.target?.python_version || "未指定"], ["GPU", data.target?.gpu || "none"], ["依存戦略", data.dependency_plan?.kind || "不明"]].forEach(([label,value]) => {
    const dt=document.createElement("dt"); dt.textContent=label; const dd=document.createElement("dd"); dd.textContent=String(value || "-"); targetFacts.append(dt,dd);
  });

  fillList("setupDependencyFiles", data.detected?.dependency_files || []);
  fillList("setupDeclaredDependencies", (data.detected?.declared_dependencies || []).map(x => `${x.name}  ← ${x.source}`));
  fillList("setupImportCandidates", data.dependency_plan?.import_only_candidates || []);
  fillList("setupEnvironmentVariables", (data.detected?.environment_variables || []).map(x => `${x.name}  ← ${x.source}`));

  const commands = byId("setupCommands"); commands.innerHTML = "";
  if (!data.commands?.length) commands.textContent = "安全に自動生成できるコマンドはありませんでした。";
  (data.commands || []).forEach((row,index) => {
    const box=document.createElement("div"); box.className="setup-command";
    const head=document.createElement("div"); head.className="symbol-head";
    const strong=document.createElement("strong"); strong.textContent=`${index+1}. ${row.title}`; head.append(strong, createBadge(row.confidence || "unknown", row.confidence === "high" ? "fact" : "warning"));
    const pre=document.createElement("pre"); pre.textContent=row.command || ""; box.append(head,pre);
    if (row.note) { const p=document.createElement("p"); p.className="muted mini"; p.textContent=row.note; box.appendChild(p); }
    commands.appendChild(box);
  });

  const findings = byId("setupFindings"); findings.innerHTML = "";
  (data.reproducibility_findings || []).forEach(row => {
    const box=document.createElement("div"); box.className=`setup-finding ${row.status || "info"}`;
    const strong=document.createElement("strong"); strong.textContent=row.title || row.status; const p=document.createElement("p"); p.className="muted mini"; p.textContent=row.detail || ""; box.append(strong,p); findings.appendChild(box);
  });
  if (!data.reproducibility_findings?.length) findings.textContent = "特記事項なし";

  const generated = byId("setupGeneratedFiles"); generated.innerHTML = "";
  (data.generated_files || []).forEach((doc,index) => {
    const details=document.createElement("details"); details.className="file-card project-doc-card"; if (index===0) details.open=true;
    const summary=document.createElement("summary"); const title=document.createElement("strong"); title.textContent=doc.filename; const desc=document.createElement("span"); desc.textContent=doc.description || ""; summary.append(title,desc);
    const body=document.createElement("div"); body.className="file-card-body"; const actions=document.createElement("div"); actions.className="doc-actions";
    const save=document.createElement("button"); save.type="button"; save.className="secondary compact"; save.textContent=`${doc.filename} 保存`; save.addEventListener("click",()=>downloadText(doc.content,doc.filename,"text/plain;charset=utf-8")); actions.appendChild(save);
    const pre=document.createElement("pre"); pre.className="doc-preview"; pre.textContent=doc.content || ""; body.append(actions,pre); details.append(summary,body); generated.appendChild(details);
  });

  byId("setupJson").textContent = JSON.stringify(data,null,2);
  byId("setupResultArea").classList.remove("hidden");
  byId("singleResultArea").classList.add("hidden");
  byId("projectResultArea").classList.add("hidden");
  byId("setupResultArea").scrollIntoView({behavior:"smooth", block:"start"});
}

byId("setupForm").addEventListener("submit", async (event) => {
  event.preventDefault(); clearError();
  const classified = classifiedSetupFiles();
  const files = classified.filter(item => item.mode === "static" || item.mode === "structure");
  if (!files.length) { showError("環境構築用に静的解析できるファイルがありません。"); return; }
  const maxFiles = appStatus?.limits?.max_environment_files || 200;
  if (files.length > maxFiles) { showError(`環境スキャン対象が ${files.length} 件あります。Environment Setup Modeの上限 ${maxFiles} 件以内で試してください。`); return; }
  byId("setupAnalyzeButton").disabled = true; setupFiles = [];
  const projectName = projectNameFromFiles(Array.from(byId("setupFolderInput").files));
  try {
    for (let i=0;i<files.length;i++) {
      const item=files[i]; const file=item.file; const path=normalizedRelativePath(file);
      setLoading(`Environment Setup ${i+1}/${files.length}: ${path}\n静的解析のみ（Ollama呼び出しなし）`);
      const params=new URLSearchParams({path});
      const res=await fetch(`/api/project/environment/analyze-file?${params}`, {method:"POST",headers:{"Content-Type":"application/octet-stream"},body:file});
      const data=await res.json(); if(!res.ok) throw new Error(`${path}: ${data.detail || "静的解析に失敗しました"}`);
      if (data.processing?.mode !== "skip") setupFiles.push(data);
    }
    if (!setupFiles.length) throw new Error("環境構築計画に利用できるファイルがありませんでした。");
    setLoading("静的解析結果と対象OSから環境構築プランを作成しています…");
    const payload={project_name:projectName,target_os:byId("targetOs").value,shell:byId("targetShell").value,python_version:byId("targetPythonVersion").value.trim(),gpu:byId("targetGpu").value,files:setupFiles};
    const res=await fetch("/api/project/environment-plan", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const data=await res.json(); if(!res.ok) throw new Error(data.detail || "環境構築プラン生成に失敗しました");
    renderSetupResult(data);
  } catch(error) { showError(error.message); }
  finally { byId("setupAnalyzeButton").disabled=false; clearLoading(); renderSetupFolderPreview(); }
});

function renderProjectPairList(id, items, keyName, valueName) {
  const el = byId(id); el.innerHTML = ""; if (!items?.length) { el.textContent = "特記事項なし"; return; }
  items.forEach(item => { const box = document.createElement("div"); box.className = "symbol"; const strong = document.createElement("strong"); strong.textContent = item[keyName] || "不明"; const p = document.createElement("p"); p.className = "symbol-meta"; p.textContent = item[valueName] || ""; box.append(strong, p); el.appendChild(box); });
}
function renderProjectResult(summary, fileResults, skippedFiles = [], excludedFiles = []) {
  const verifiedFiles = summary.files?.length ? summary.files : fileResults;
  lastProjectResult = {...summary, files: verifiedFiles, skipped_files: skippedFiles, excluded_files: excludedFiles, project_qa_history: []}; lastProjectDocs = null; byId("projectDocsArea").classList.add("hidden"); byId("projectDocsList").innerHTML = ""; resetProjectChat(); const a = summary.analysis; const idx = summary.project_index;
  const pc = idx.processing_counts || {}; const llmCount = pc.llm || 0; const structureCount = pc.structure || 0;
  const removedClaims = summary.grounding?.removed_claim_count || 0;
  byId("projectTitle").textContent = summary.project.name; byId("projectMeta").textContent = `${summary.project.file_count} included / LLM ${llmCount} / structure ${structureCount} / grounded ${removedClaims} claims / skipped ${skippedFiles.length} / excluded ${excludedFiles.length} / model: ${summary.model}`;
  const facts = byId("projectFacts"); facts.innerHTML = ""; [["プロジェクト要約対象", idx.file_count], ["LLM個別解析", llmCount], ["構造のみ", structureCount], ["静的照合で除外したLLM主張", removedClaims], ["スキップ", skippedFiles.length], ["除外", excludedFiles.length], ["総行数", idx.total_lines], ["依存エッジ", idx.local_dependency_edges?.length || 0]].forEach(([k,v]) => { const dt=document.createElement("dt");dt.textContent=k;const dd=document.createElement("dd");dd.textContent=v;facts.append(dt,dd); });
  fillList("projectLanguages", (idx.languages || []).map(x => `${x.language}: ${x.files} files`));
  const edges = byId("dependencyEdges"); edges.innerHTML = ""; if (!idx.local_dependency_edges?.length) edges.textContent = "プロジェクト内import/includeの直接一致は検出されませんでした。"; else idx.local_dependency_edges.forEach(e => { const row=document.createElement("div");row.className="dependency-edge";row.textContent=`${e.source} → ${e.target}`;const small=document.createElement("span");small.textContent=`根拠: ${e.evidence}`;row.appendChild(small);edges.appendChild(row); }); byId("dependencyNote").textContent = idx.note || "";
  const skipList = byId("projectSkippedFiles"); skipList.innerHTML = ""; const ignored = [...skippedFiles, ...excludedFiles]; if (!ignored.length) skipList.textContent="なし"; else ignored.slice(0,80).forEach(item => { const li=document.createElement("li"); li.textContent=`${item.path} — ${item.reason}`; skipList.appendChild(li); });
  byId("projectPurpose").textContent = a.purpose || ""; byId("projectOverview").textContent = a.overview || ""; fillList("architectureFlow", a.architecture_flow, {stripLeadingNumber:true}); renderProjectPairList("entryPoints", a.entry_points, "path", "reason"); renderProjectPairList("readFirst", a.read_first, "path", "reason");
  fillList("configDataFiles", a.config_and_data_files); fillList("projectDependencies", idx.external_dependencies); fillList("projectRisks", a.change_risks); fillList("projectUnknowns", a.unknowns);
  renderProjectPairList("projectComponents", a.components, "path", "role");
  const cards = byId("projectFileCards"); cards.innerHTML = ""; verifiedFiles.forEach(item => { const card=document.createElement("details");card.className="file-card";const summaryEl=document.createElement("summary");const title=document.createElement("strong");title.textContent=item.file.path;const desc=document.createElement("span");desc.textContent=item.analysis.purpose || "";summaryEl.append(title,desc);const body=document.createElement("div");body.className="file-card-body";const overview=document.createElement("p");overview.textContent=item.analysis.overview || "";const meta=document.createElement("p");meta.className="muted mini";const mode=item.processing?.mode || "llm";const removed=item.grounding?.removed_claim_count || 0;meta.textContent=`${item.file.language} / ${item.file.line_count} lines / ${mode === "structure" ? "構造のみ・LLMなし" : `model: ${item.model || summary.model}`} / grounding除外 ${removed}`;const facts=document.createElement("p");facts.className="muted mini";const deps=item.verified_facts?.external_dependencies || item.analysis.external_dependencies || [];const related=item.verified_facts?.related_files || item.analysis.related_files || [];facts.textContent=`確認済み外部依存: ${deps.length ? deps.join(", ") : "なし"} / 関連ファイル: ${related.length ? related.join(", ") : "なし"}`;body.append(meta,overview,facts);card.append(summaryEl,body);cards.appendChild(card); });
  byId("projectJson").textContent = JSON.stringify(lastProjectResult, null, 2); byId("projectResultArea").classList.remove("hidden"); byId("singleResultArea").classList.add("hidden"); byId("setupResultArea").classList.add("hidden");
}

byId("projectForm").addEventListener("submit", async (event) => {
  event.preventDefault(); clearError(); const classified = classifiedProjectFiles();
  const files = classified.filter(item => item.mode === "llm" || item.mode === "structure");
  projectSkipped = classified.filter(item => item.mode === "skip").map(item => ({path:normalizedRelativePath(item.file), reason:item.reason}));
  projectExcluded = classified.filter(item => item.mode === "exclude").map(item => ({path:normalizedRelativePath(item.file), reason:item.reason}));
  if (!files.length) { showError("LLM解析または構造解析の対象になるファイルがありません。"); return; }
  const maxFiles = appStatus?.limits?.max_project_files || 40; if (files.length > maxFiles) { showError(`解析対象が ${files.length} 件あります。v3.5の上限 ${maxFiles} 件以内のフォルダで試してください。`); return; }
  byId("projectAnalyzeButton").disabled = true; projectFiles = []; const projectName = projectNameFromFiles(Array.from(byId("folderInput").files)); const model = byId("modelInput").value.trim();
  try {
    for (let i=0;i<files.length;i++) {
      const item = files[i]; const file = item.file; const path = normalizedRelativePath(file); const stage = item.mode === "structure" ? "構造解析（LLM個別解析なし）" : "静的解析 → Ollama個別要約"; setLoading(`プロジェクト解析 ${i+1}/${files.length}: ${path}\n${stage}`); const params = new URLSearchParams({path, model}); const res = await fetch(`/api/project/analyze-file?${params}`, {method:"POST", headers:{"Content-Type":"application/octet-stream"}, body:file}); const data = await res.json(); if (!res.ok) throw new Error(`${path}: ${data.detail || "解析に失敗しました"}`);
      if (data.processing?.mode === "skip") projectSkipped.push({path, reason:data.processing.reason || "サーバー側でスキップ"}); else projectFiles.push(data);
    }
    if (!projectFiles.length) { throw new Error("内容確認後、プロジェクト要約に使えるファイルがありませんでした。"); }
    setLoading(`ファイル処理完了: ${projectFiles.length} included / ${projectSkipped.length} skipped\nプロジェクト全体をOllamaで整理しています…`);
    const res = await fetch("/api/project/summarize", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({project_name:projectName, model, files:projectFiles})}); const summary = await res.json(); if (!res.ok) throw new Error(summary.detail || "プロジェクト要約に失敗しました"); projectFiles = summary.files?.length ? summary.files : projectFiles; renderProjectResult(summary, projectFiles, projectSkipped, projectExcluded);
  } catch (error) { showError(error.message); } finally { byId("projectAnalyzeButton").disabled = false; clearLoading(); renderFolderPreview(); }
});

byId("projectAskForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!lastProjectResult) return;
  const question = byId("projectQuestionInput").value.trim();
  if (!question) return;
  const historyForRequest = projectChatHistory.slice(-8);
  appendProjectChatMessage("user", question);
  byId("projectQuestionInput").value = "";
  byId("projectAskButton").disabled = true; byId("projectQuestionInput").disabled = true; byId("projectAskStatus").textContent = "質問意図と関連ファイルを選定し、fact + 意味解釈の根拠をgrounding中…";
  try {
    const payload = {
      project_name: lastProjectResult.project.name,
      model: byId("modelInput").value.trim(),
      question,
      project_index: lastProjectResult.project_index,
      analysis: lastProjectResult.analysis,
      files: lastProjectResult.files,
      history: historyForRequest,
    };
    const res = await fetch("/api/project/ask", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "プロジェクト質問への回答に失敗しました");
    appendProjectChatMessage("assistant", data.answer, data.model, data);
    projectChatHistory.push({role:"user", content:question}, {role:"assistant", content:data.answer}); projectChatHistory = projectChatHistory.slice(-8);
    lastProjectResult.project_qa_history.push({question, answer:data.answer, evidence:data.evidence, fact_ids:data.fact_ids, confidence:data.confidence, limitations:data.limitations, context_selection:data.context_selection, grounding:data.grounding, model:data.model, metrics:data.metrics});
    byId("projectJson").textContent = JSON.stringify(lastProjectResult, null, 2);
    byId("projectAskStatus").textContent = "";
  } catch (error) {
    appendProjectChatMessage("assistant", `エラー: ${error.message}`); byId("projectAskStatus").textContent = "回答に失敗しました。";
  } finally {
    byId("projectAskButton").disabled = false; byId("projectQuestionInput").disabled = false; byId("projectQuestionInput").focus();
  }
});
byId("clearProjectChatButton").addEventListener("click", resetProjectChat);
document.querySelectorAll(".project-quick-question").forEach(button => button.addEventListener("click", () => { byId("projectQuestionInput").value = button.dataset.question || ""; byId("projectQuestionInput").focus(); }));


function downloadText(content, filename, type = "text/markdown;charset=utf-8") {
  const blob = new Blob([content || ""], {type});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function renderProjectDocs(data) {
  lastProjectDocs = data;
  const area = byId("projectDocsArea");
  const list = byId("projectDocsList");
  list.innerHTML = "";
  const meta = data.generation || {};
  byId("projectDocsMeta").textContent = `${data.documents?.length || 0} files / source: ${meta.source || "grounded_project_analysis"} / source code embedded: ${meta.source_code_embedded ? "yes" : "no"} / extra Ollama call: ${meta.extra_ollama_call ? "yes" : "no"}`;
  (data.documents || []).forEach((doc, index) => {
    const details = document.createElement("details");
    details.className = "file-card project-doc-card";
    if (index === 0) details.open = true;
    const summary = document.createElement("summary");
    const title = document.createElement("strong"); title.textContent = doc.filename;
    const desc = document.createElement("span"); desc.textContent = doc.description || "";
    summary.append(title, desc);
    const body = document.createElement("div"); body.className = "file-card-body";
    const actions = document.createElement("div"); actions.className = "doc-actions";
    const save = document.createElement("button"); save.type = "button"; save.className = "secondary compact"; save.textContent = `${doc.filename} 保存`;
    save.addEventListener("click", () => downloadText(doc.content, doc.filename));
    actions.appendChild(save);
    const pre = document.createElement("pre"); pre.className = "doc-preview"; pre.textContent = doc.content || "";
    body.append(actions, pre); details.append(summary, body); list.appendChild(details);
  });
  area.classList.remove("hidden");
  area.scrollIntoView({behavior:"smooth", block:"start"});
}

async function generateProjectDocs() {
  if (!lastProjectResult) return;
  clearError();
  const button = byId("projectDocsButton");
  const regen = byId("regenerateProjectDocsButton");
  button.disabled = true; regen.disabled = true;
  setLoading("grounding済み解析結果から README / ARCHITECTURE / HANDOVER を生成しています…");
  try {
    const payload = {
      project_name: lastProjectResult.project.name,
      project_index: lastProjectResult.project_index,
      analysis: lastProjectResult.analysis,
      files: lastProjectResult.files,
    };
    const res = await fetch("/api/project/generate-docs", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "引き継ぎ資料の生成に失敗しました");
    renderProjectDocs(data);
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false; regen.disabled = false; clearLoading();
  }
}

function downloadJson(data, filename) { if (!data) return; const blob = new Blob([JSON.stringify(data, null, 2)], {type:"application/json"}); const url = URL.createObjectURL(blob); const a=document.createElement("a");a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url); }
byId("projectDocsButton").addEventListener("click", generateProjectDocs);
byId("regenerateProjectDocsButton").addEventListener("click", generateProjectDocs);
byId("projectDownloadButton").addEventListener("click", () => downloadJson(lastProjectResult, `${lastProjectResult?.project?.name || "project"}.project-analysis.json`));
byId("setupDownloadButton").addEventListener("click", () => downloadJson(lastSetupResult, `${lastSetupResult?.project?.name || "project"}.environment-plan.json`));

loadStatus();
