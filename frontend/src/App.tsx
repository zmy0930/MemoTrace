import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Brain,
  Database,
  FileUp,
  GitBranch,
  Globe2,
  HeartPulse,
  History,
  NotebookText,
  Network,
  RefreshCcw,
  Send,
  Settings,
  Sparkles,
  Trash2
} from "lucide-react";
import {
  acceptWikiProposal,
  acceptCandidate,
  askQuestion,
  deleteCard,
  distillPreferences,
  generateContent,
  getKnowledgeGraph,
  getProfile,
  getWikiIndex,
  getWikiLog,
  healthCheck,
  listCandidates,
  listCards,
  listQASessions,
  listStaging,
  listSystemLogs,
  listWikiProposals,
  mergeStaging,
  rejectCandidate,
  rejectWikiProposal,
  reviewHealth,
  runWebCompletion,
  saveFeedback,
  uploadDocuments
} from "./api";
import type {
  AskResponse,
  CardInfo,
  HealthReviewResponse,
  KnowledgeGraphInfo,
  ModelSettings,
  PreferenceCandidate,
  QASessionInfo,
  StagingItemInfo,
  SystemLogInfo,
  UserProfile,
  WikiPageInfo,
  WikiProposalInfo
} from "./types";

type TabKey = "qa" | "wiki" | "graph" | "health" | "memory" | "logs" | "generate" | "settings";

const defaultModelSettings: ModelSettings = {
  apiKey: "",
  baseUrl: "https://llm-22mos6q60zk2xrra.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
  textModel: "qwen3-vl-plus",
  visionModel: "qwen3-vl-plus",
  embeddingModel: "text-embedding-v4"
};

const tabs: Array<{ key: TabKey; label: string; icon: typeof Database }> = [
  { key: "qa", label: "问答溯源", icon: Send },
  { key: "wiki", label: "Wiki", icon: Database },
  { key: "graph", label: "Graph", icon: Network },
  { key: "health", label: "健康审查", icon: HeartPulse },
  { key: "memory", label: "偏好记忆", icon: Brain },
  { key: "logs", label: "运行日志", icon: Activity },
  { key: "generate", label: "内容生成", icon: NotebookText },
  { key: "settings", label: "模型配置", icon: Settings }
];

export function App() {
  const [status, setStatus] = useState("正在连接后端");
  const [activeTab, setActiveTab] = useState<TabKey>("qa");
  const [cards, setCards] = useState<CardInfo[]>([]);
  const [logs, setLogs] = useState<SystemLogInfo[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [stagingItems, setStagingItems] = useState<StagingItemInfo[]>([]);
  const [wikiIndex, setWikiIndex] = useState<WikiPageInfo | null>(null);
  const [wikiLog, setWikiLog] = useState<WikiPageInfo | null>(null);
  const [wikiProposals, setWikiProposals] = useState<WikiProposalInfo[]>([]);
  const [knowledgeGraph, setKnowledgeGraph] = useState<KnowledgeGraphInfo | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [qaSessions, setQaSessions] = useState<QASessionInfo[]>([]);
  const [modelSettings, setModelSettings] = useState<ModelSettings>(() => {
    const saved = localStorage.getItem("tracewiki.modelSettings");
    if (!saved) return defaultModelSettings;
    try {
      return { ...defaultModelSettings, ...JSON.parse(saved) };
    } catch {
      return defaultModelSettings;
    }
  });
  const [question, setQuestion] = useState("这个知识库目前有哪些核心能力？");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackAction, setFeedbackAction] = useState("accepted");
  const [health, setHealth] = useState<HealthReviewResponse | null>(null);
  const [webQuery, setWebQuery] = useState("个人知识库智能助手 RAG 多模态 可回溯");
  const [candidates, setCandidates] = useState<PreferenceCandidate[]>([]);
  const [generated, setGenerated] = useState("");
  const [busy, setBusy] = useState(false);

  const spanEvidenceCount = useMemo(
    () => answer?.evidence.filter((item) => item.locator !== "wiki_card").length ?? 0,
    [answer]
  );

  async function refreshAll() {
    const [cardItems, logItems, profileInfo, pendingItems, indexPage, logPage, proposalItems, graphInfo, qaSessionItems] = await Promise.all([
      listCards(),
      listSystemLogs(),
      getProfile(),
      listStaging(),
      getWikiIndex(),
      getWikiLog(),
      listWikiProposals(),
      getKnowledgeGraph(),
      listQASessions()
    ]);
    setCards(cardItems);
    setLogs(logItems);
    setProfile(profileInfo);
    setStagingItems(pendingItems);
    setWikiIndex(indexPage);
    setWikiLog(logPage);
    setWikiProposals(proposalItems);
    setKnowledgeGraph(graphInfo);
    setQaSessions(qaSessionItems);
  }

  useEffect(() => {
    healthCheck()
      .then(() => refreshAll())
      .then(() => setStatus("后端已连接"))
      .catch(() => setStatus("未连接 FastAPI 后端"));
  }, []);

  useEffect(() => {
    localStorage.setItem("tracewiki.modelSettings", JSON.stringify(modelSettings));
  }, [modelSettings]);

  async function handleUpload() {
    if (!files.length) return;
    setBusy(true);
    try {
      const result = await uploadDocuments(files, modelSettings);
      setStatus(result.message);
      setFiles([]);
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAsk() {
    setBusy(true);
    try {
      const result = await askQuestion(question, 5, modelSettings);
      setAnswer(result);
      setStatus(`已生成回答，召回 ${result.evidence.length} 条证据`);
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "提问失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleFeedback() {
    if (!answer) return;
    await saveFeedback({
      question,
      answer_summary: answer.answer.slice(0, 600),
      answer_type: "technical_explanation",
      user_feedback: feedback,
      user_action: feedbackAction,
      accepted: feedbackAction !== "not_helpful"
    });
    setFeedback("");
    setStatus("反馈已保存，可进入偏好记忆蒸馏");
    await refreshAll();
  }

  async function handleHealth() {
    setBusy(true);
    try {
      const result = await reviewHealth(modelSettings);
      setHealth(result);
      setStatus(`健康审查完成，发现 ${result.issues.length} 个问题`);
      if (result.completion_actions[0]?.query_or_request) {
        setWebQuery(result.completion_actions[0].query_or_request);
      }
      await refreshAll();
    } finally {
      setBusy(false);
    }
  }

  async function handleWebCompletion() {
    if (!webQuery.trim()) return;
    setBusy(true);
    try {
      const items = await runWebCompletion(webQuery, 3);
      setStagingItems(items);
      setStatus(`联网补全已暂存 ${items.length} 条候选，确认后才会合并进知识库`);
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "联网补全失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleMergeStaging(stagingId: string) {
    setBusy(true);
    try {
      const card = await mergeStaging(stagingId);
      setStatus(`已合并网页资料：${card.title}`);
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "合并失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAcceptWikiProposal(proposalId: string) {
    setBusy(true);
    try {
      await acceptWikiProposal(proposalId, modelSettings);
      setStatus("LLM 维护提案已接受并应用");
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "接受提案失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRejectWikiProposal(proposalId: string) {
    setBusy(true);
    try {
      await rejectWikiProposal(proposalId);
      setStatus("LLM 维护提案已拒绝");
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "拒绝提案失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteCard(cardId: string) {
    if (!window.confirm("确认删除这张 Wiki 卡片及其证据索引吗？")) return;
    setBusy(true);
    try {
      await deleteCard(cardId);
      setStatus("Wiki 卡片已删除，相关证据和向量索引已清理");
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDistill() {
    const result = await distillPreferences();
    setCandidates(result);
    setStatus(`生成 ${result.length} 条偏好候选`);
    await refreshAll();
  }

  async function refreshCandidates() {
    setCandidates(await listCandidates());
  }

  async function handleGenerate(kind: "note" | "report" | "ppt" | "mindmap") {
    const result = await generateContent(kind);
    setGenerated(result.content);
    setStatus(`已生成 ${kind}`);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>TraceWiki</h1>
          <p>{status}</p>
        </div>
        <div className="metrics" aria-label="知识库指标">
          <span><Database size={16} />{cards.length} Wiki</span>
          <span><GitBranch size={16} />{spanEvidenceCount} Span</span>
          <button className="icon-button" type="button" onClick={refreshAll} title="刷新">
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      <section className="upload-band">
        <label className="file-picker">
          <FileUp size={18} />
          <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
          <span>{files.length ? `${files.length} 个文件` : "选择资料文件"}</span>
        </label>
        <button className="primary-button" disabled={!files.length || busy} onClick={handleUpload} type="button">
          摄入并生成 Wiki
        </button>
      </section>

      <nav className="tabs" aria-label="功能区">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              className={activeTab === tab.key ? "active" : ""}
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              type="button"
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {activeTab === "qa" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>知识问答</h2>
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
            <button className="primary-button" disabled={busy} onClick={handleAsk} type="button">
              <Send size={16} />
              提问
            </button>
            <div className="feedback-row">
              <select value={feedbackAction} onChange={(event) => setFeedbackAction(event.target.value)}>
                <option value="accepted">整体可用</option>
                <option value="add_code">多给代码</option>
                <option value="add_table">多给表格</option>
                <option value="add_steps">多给步骤</option>
                <option value="make_shorter">更短</option>
                <option value="make_more_detailed">更详细</option>
                <option value="make_ppt">适合 PPT</option>
                <option value="not_helpful">没帮助</option>
              </select>
              <input value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="补充反馈" />
              <button type="button" onClick={handleFeedback} disabled={!answer}>保存反馈</button>
            </div>
          </div>
          <div className="panel">
            <h2>回答与证据</h2>
            {answer ? (
              <>
                <pre className="markdown-block">{answer.answer}</pre>
                <h3>证据工作图</h3>
                <pre className="code-block">{answer.graph_mermaid}</pre>
                <h3>证据片段</h3>
                <div className="evidence-list">
                  {answer.evidence.map((item, index) => (
                    <article key={`${item.source}-${index}`}>
                      <strong>{item.title}</strong>
                      <span>{item.locator} · score {item.score.toFixed(3)}</span>
                      <p>{item.snippet}</p>
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <p className="empty">输入问题后会显示回答、SourceSpan 证据和可复制的 Mermaid 图。</p>
            )}
          </div>
        </section>
      ) : null}

      {activeTab === "wiki" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>Wiki 卡片</h2>
            <div className="wiki-list">
              {cards.map((card) => (
                <article key={card.card_id}>
                  <strong>{card.title}</strong>
                  <span>{card.category} · {card.tags.join(", ")}</span>
                  <p>{card.summary}</p>
                  <div className="button-row">
                    <button onClick={() => handleDeleteCard(card.card_id)} disabled={busy} type="button" title="删除 Wiki 卡片">
                      <Trash2 size={15} />
                      删除
                    </button>
                  </div>
                  <details>
                    <summary>查看 Markdown</summary>
                    <pre>{card.content}</pre>
                  </details>
                </article>
              ))}
            </div>
          </div>
          <div className="panel">
            <h2>LLM Wiki 目录</h2>
            <pre className="markdown-block">{wikiIndex?.content || "index.md 会在摄入资料后自动生成。"}</pre>
            <h3>活动日志</h3>
            <pre className="markdown-block">{wikiLog?.content || "log.md 会记录摄入、检索、回答和补全事件。"}</pre>
            <h3>LLM 维护提案</h3>
            {wikiProposals.length ? (
              wikiProposals.map((proposal) => (
                <article className="line-item" key={proposal.proposal_id}>
                  <strong>{proposal.title}</strong>
                  <span>{proposal.proposal_type} · {proposal.created_at}</span>
                  <p>{proposal.rationale}</p>
                  <details>
                    <summary>查看拟修改内容</summary>
                    <pre>{proposal.proposed_content}</pre>
                  </details>
                  <div className="button-row">
                    <button onClick={() => handleAcceptWikiProposal(proposal.proposal_id)} disabled={busy} type="button">
                      接受并应用
                    </button>
                    <button onClick={() => handleRejectWikiProposal(proposal.proposal_id)} disabled={busy} type="button">
                      拒绝
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <p className="empty">配置 LLM 后，旧页更新、冲突审查、问答沉淀会先进入这里等待确认。</p>
            )}
          </div>
        </section>
      ) : null}

      {activeTab === "graph" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>Knowledge Graph</h2>
            <div className="graph-stats">
              {Object.entries(knowledgeGraph?.stats ?? {}).map(([key, value]) => (
                <span key={key}>{key}: {value}</span>
              ))}
            </div>
            <h3>Communities</h3>
            <div className="graph-list compact-graph-list">
              {(knowledgeGraph?.communities ?? []).map((community) => (
                <article key={community.id} className="graph-community">
                  <strong>{community.label}</strong>
                  <span>{community.size} cards · {community.span_count} spans</span>
                  <p>{community.card_titles.join(", ")}</p>
                </article>
              ))}
            </div>
            <h3>Nodes</h3>
            <div className="graph-list">
              {(knowledgeGraph?.nodes ?? []).map((node) => (
                <article key={node.id} className={`graph-node graph-node-${node.type}`}>
                  <strong>{node.label}</strong>
                  <span>{node.type}</span>
                </article>
              ))}
            </div>
          </div>
          <div className="panel">
            <h2>Relations</h2>
            <div className="graph-list">
              {(knowledgeGraph?.edges ?? []).map((edge) => (
                <article key={edge.id} className="line-item">
                  <strong>{edge.type}</strong>
                  <span>{`${edge.source} -> ${edge.target}`}</span>
                  <p>{edge.label} · weight {edge.weight.toFixed(2)}</p>
                </article>
              ))}
            </div>
            {!knowledgeGraph?.nodes.length ? (
              <p className="empty">Upload knowledge files first. The graph is generated from Wiki cards, SourceSpan evidence, tags, categories, and [[Wiki Links]].</p>
            ) : null}
          </div>
        </section>
      ) : null}

      {activeTab === "health" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>知识库健康审查</h2>
            <button className="primary-button" onClick={handleHealth} disabled={busy} type="button">
              <HeartPulse size={16} />
              开始审查
            </button>
            {health ? (
              <pre className="markdown-block">{health.report_markdown}</pre>
            ) : (
              <p className="empty">审查后会列出缺来源、覆盖不足、多模态缺失等问题。</p>
            )}
          </div>
          <div className="panel">
            <h2>补全工作台</h2>
            <div className="web-completion-box">
              <input
                value={webQuery}
                onChange={(event) => setWebQuery(event.target.value)}
                placeholder="输入要自动搜索补全的主题"
              />
              <button className="primary-button" onClick={handleWebCompletion} disabled={busy || !webQuery.trim()} type="button">
                <Globe2 size={16} />
                联网补全到暂存区
              </button>
            </div>
            {health?.completion_actions.map((action) => (
              <article className="line-item" key={action.issue_title}>
                <strong>{action.action_type}</strong>
                <p>{action.query_or_request}</p>
                <span>{action.rationale}</span>
              </article>
            ))}
            <h3>待确认网页资料</h3>
            {stagingItems.length ? (
              stagingItems.map((item) => (
                <article className="line-item" key={item.staging_id}>
                  <strong>{item.title}</strong>
                  <span>{item.url}</span>
                  <p>{item.summary}</p>
                  <div className="button-row">
                    <button onClick={() => handleMergeStaging(item.staging_id)} disabled={busy} type="button">
                      确认合并
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <p className="empty">联网补全会先进入暂存区，确认后才写入 raw/web 并生成 Wiki。</p>
            )}
          </div>
        </section>
      ) : null}

      {activeTab === "memory" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>当前用户画像</h2>
            <pre className="code-block">{profile ? JSON.stringify(profile, null, 2) : "未加载"}</pre>
          </div>
          <div className="panel">
            <h2>偏好候选</h2>
            <div className="button-row">
              <button className="primary-button" onClick={handleDistill} type="button">
                <Sparkles size={16} />
                从历史蒸馏
              </button>
              <button type="button" onClick={refreshCandidates}>刷新候选</button>
            </div>
            {candidates.map((candidate) => (
              <article className="line-item" key={candidate.candidate_id}>
                <strong>{`${candidate.field}: ${candidate.old_value} -> ${candidate.new_value}`}</strong>
                <p>{candidate.evidence}</p>
                <span>confidence {candidate.confidence.toFixed(2)}</span>
                <div className="button-row">
                  <button onClick={() => acceptCandidate(candidate.candidate_id).then(refreshAll)} type="button">接受</button>
                  <button onClick={() => rejectCandidate(candidate.candidate_id).then(refreshCandidates)} type="button">拒绝</button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeTab === "logs" ? (
        <section className="workspace">
          <div className="panel">
            <h2>系统运行日志</h2>
            {logs.map((log) => (
              <article className="line-item" key={log.log_id}>
                <strong>{log.action_type}</strong>
                <span>{log.created_at}</span>
                <p>{log.summary}</p>
                <pre>{JSON.stringify(log.payload, null, 2)}</pre>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeTab === "generate" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>内容生成</h2>
            <div className="button-grid">
              <button onClick={() => handleGenerate("note")} type="button">学习笔记</button>
              <button onClick={() => handleGenerate("report")} type="button">技术报告</button>
              <button onClick={() => handleGenerate("ppt")} type="button">PPT 大纲</button>
              <button onClick={() => handleGenerate("mindmap")} type="button">思维导图</button>
            </div>
          </div>
          <div className="panel">
            <h2>生成结果</h2>
            <pre className="markdown-block">{generated || "选择一种输出类型。"}</pre>
          </div>
        </section>
      ) : null}

      {activeTab === "settings" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>模型配置</h2>
            <div className="settings-grid">
              <label>
                <span>API Key</span>
                <input
                  type="password"
                  value={modelSettings.apiKey}
                  onChange={(event) => setModelSettings({ ...modelSettings, apiKey: event.target.value })}
                  placeholder="sk-..."
                />
              </label>
              <label>
                <span>Base URL</span>
                <input
                  value={modelSettings.baseUrl}
                  onChange={(event) => setModelSettings({ ...modelSettings, baseUrl: event.target.value })}
                />
              </label>
              <label>
                <span>Text Model</span>
                <input
                  value={modelSettings.textModel}
                  onChange={(event) => setModelSettings({ ...modelSettings, textModel: event.target.value })}
                />
              </label>
              <label>
                <span>Vision Model</span>
                <input
                  value={modelSettings.visionModel}
                  onChange={(event) => setModelSettings({ ...modelSettings, visionModel: event.target.value })}
                />
              </label>
              <label>
                <span>Embedding Model</span>
                <input
                  value={modelSettings.embeddingModel}
                  onChange={(event) => setModelSettings({ ...modelSettings, embeddingModel: event.target.value })}
                />
              </label>
            </div>
            <p className="empty">配置保存在浏览器本地，请不要把真实 API Key 提交到仓库。</p>
          </div>
          <div className="panel">
            <h2><History size={18} /> 最近问答</h2>
            <div className="history-list">
              {qaSessions.map((session) => (
                <article className="line-item" key={session.session_id}>
                  <strong>{session.question}</strong>
                  <span>{session.created_at} · {session.evidence.length} evidence</span>
                  <p>{session.answer.slice(0, 260)}</p>
                </article>
              ))}
              {!qaSessions.length ? <p className="empty">还没有问答历史。</p> : null}
            </div>
          </div>
        </section>
      ) : null}
    </main>
  );
}
