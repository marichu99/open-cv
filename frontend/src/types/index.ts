export type Role = "agent" | "campaign_manager" | "coordinator" | "admin" | "viewer";

export interface Agent {
  id: string;
  full_name: string;
  phone_number: string;
  email: string | null;
  phone_verified: boolean;
  role: Role;
  assigned_station_id: string | null;
  position_ids: string[];
}

export interface AgentWithAssignment extends Agent {
  assigned_station_name: string | null;
  ward_name: string | null;
  constituency_name: string | null;
  county_name: string | null;
  position_names: string[];
}

export interface County {
  id: string;
  name: string;
  registered_voters: number | null;
}

export interface Constituency {
  id: string;
  county_id: string;
  name: string;
  registered_voters: number | null;
}

export interface Ward {
  id: string;
  constituency_id: string;
  name: string;
}

export interface PollingStation {
  id: string;
  ward_id: string;
  iebc_code: string | null;
  name: string;
  registered_voters: number | null;
  stream_count: number;
}

export type PositionLevel = "national" | "county" | "constituency" | "ward";

export interface ElectivePosition {
  id: string;
  name: string;
  form_series: string;
  level: PositionLevel;
}

export type GroupingLevel = "county" | "constituency" | "ward" | "station";

export interface PositionWithData extends ElectivePosition {
  has_data: boolean;
  scopes: { id: string; name: string }[];
  grouping_levels: GroupingLevel[];
}

export interface Candidate {
  id: string;
  position_id: string;
  county_id: string | null;
  constituency_id: string | null;
  ward_id: string | null;
  full_name: string;
  party: string | null;
}

export type SubmissionStatus =
  | "draft"
  | "auto_approved"
  | "pending_review"
  | "manually_approved"
  | "rejected"
  | "duplicate";

export interface VoteRecord {
  id: string;
  candidate_id: string;
  candidate_name: string;
  votes_detected: number;
  votes_corrected: number | null;
  effective_votes: number;
  field_confidence: number;
  manually_overridden: boolean;
}

export interface VerificationLogEntry {
  id: string;
  reviewer_id: string | null;
  reviewer_name: string | null;
  action: string;
  notes: string | null;
  created_at: string;
}

export interface FormSubmission {
  id: string;
  station_id: string;
  station_name: string;
  ward_name: string | null;
  constituency_name: string | null;
  county_name: string | null;
  agent_id: string;
  agent_name: string;
  position_id: string;
  form_type: string; // e.g. "39A" — position's form_series + level letter
  image_url: string;
  captured_at: string | null;
  uploaded_at: string;
  finalized_at: string | null;
  total_votes_cast: number | null;
  rejected_ballots: number | null;
  ocr_confidence_avg: number | null;
  status: SubmissionStatus;
  duplicate_of: string | null;
  warnings: string[];
  vote_records?: VoteRecord[];
  logs?: VerificationLogEntry[];
}

export interface TallyCandidate {
  candidate_id: string;
  full_name: string;
  party: string | null;
  votes: number;
}

export interface TallySummary {
  candidates: TallyCandidate[];
  stations_reported: number;
  stations_total: number;
}

export interface TimeseriesPoint {
  timestamp: string;
  cumulative: Record<string, number>;
}

export type TimeseriesGranularity = "second" | "minute" | "hour" | "day";

export interface Timeseries {
  candidates: { candidate_id: string; full_name: string }[];
  series: TimeseriesPoint[];
  granularity: TimeseriesGranularity;
}

export interface StationTally {
  station_id: string;
  station_name: string;
  reported_at: string | null;
  votes: Record<string, number>;
  total_votes_cast: number | null;
  rejected_ballots: number | null;
}

export interface VotesByStation {
  candidates: { candidate_id: string; full_name: string }[];
  stations: StationTally[];
}

export interface GroupTally {
  group_id: string;
  group_name: string;
  votes: Record<string, number>;
}

export interface VotesByGroup {
  candidates: { candidate_id: string; full_name: string }[];
  level: GroupingLevel;
  groups: GroupTally[];
}
