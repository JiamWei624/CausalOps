export type CheckStatus = 'verified'|'issue'|'unknown'|'not_applicable'|'not_checked';
export type DecisionKind = 'accepted'|'deferred'|'rejected'|'note';
export type Finding = {
  finding_id:string; rule:{id:string;version:string;check_method:string}; status:CheckStatus;
  result:{observed:unknown;expected:unknown;reason_code:string;missing_items:string[];required_work:string[]};
  impact:{explanation:string;claim_effect:string}; severity:{level:string;policy_id:string;reason_code:string};
  evidence_refs:unknown[];source:{origin:string};human_confirmation_required:boolean;
};
export type Suggestion = {suggestion_id:string;diagnostic_id:string;rule_id:string;action:string;reason:string;required_evidence:string[];new_scope:string;human_review_required:boolean;related_refs:unknown};
export type DiagnosticReport = {
  report_id:string;version:number;assessment_id:string;created_at:string;context:unknown;
  results:{status:string;objective:string|null;scope:{analysis_unit:string;metric_label:string;unit:string;observation_window:string;group_labels:string[]};method:string|null;
    effect:{pp:number;ci_pp:number[];control_rate:number;treated_rate:number}|null;sample_size:number|null;
    group_summary:{treatment:number;n:number;outcome_mean:number}[];
    descriptive?:{groups:{label:string;n:number;proportion:number}[];difference_pp:number;sample_size:number;interval:null};
    runs:{run_id:string;kind:string}[];limitations:string[]};
  quality:{findings:Finding[];status_labels:Record<string,string>;implemented_rules:string[];unimplemented_rules:string[];limitations:string[];conclusion_policy:string};
  suggestions:Suggestion[];model_requests:0;execution_authorized:false;
};
export type DecisionEntry = {
  decision:{decision_id:string;report_id:string;report_version:number;decision_type:DecisionKind;reason:string;suggestion_id:string|null;supersedes_id:string|null;created_at:string;execution_authorized:false;evidence_refs:unknown[];context:unknown;suggestion_action:string|null};
  origin_verified:boolean;origin_error:string|null;superseded_by:string|null;revisable_for:(string|null)[];
};
export type InsightView = {
  chat_id:string;binding_id:string;context_sha:string;mode:'preflight'|'post_run';subject_id:string;session_id:string;title:string;
  history:{id:string;version:number}[];decision_types:Record<DecisionKind,string>;
  report:DiagnosticReport|null;report_sha:string|null;source_current:boolean|null;source_error:string|null;
  decisions:DecisionEntry[];reminders:{decision_id:string;prior_report_id:string;rule_id:string;kind:string;current_status:CheckStatus|null;message:string}[];
};
export type DecisionInput = {decision_type:DecisionKind;reason:string;suggestion_id:string|null;supersedes_id:string|null};
export const ruleNames:Record<string,string>={'PD-01':'证据身份','PD-02':'随机化依据','PD-06':'观察窗口','PD-07':'双Run一致性','PD-09':'指标与单位链','PD-14':'报告来源'};
export const typeNames:Record<DecisionKind,string>={accepted:'采纳建议',deferred:'暂缓处理',rejected:'拒绝建议',note:'自主研究决定'};
