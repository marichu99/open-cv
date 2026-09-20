import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Camera, Users, Flag, ArrowLeft, ArrowRight, ClipboardCheck, User, Phone, Mail } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useCounties, useConstituencies, useWards } from "@/lib/hooks";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Combobox } from "@/components/ui/combobox";
import { OtpInput } from "@/components/ui/otp-input";
import { cn, positionLabel } from "@/lib/utils";
import type { ElectivePosition } from "@/types";

type SignupRole = "agent" | "campaign_manager" | "aspirant";

const ASPIRANT_SCOPE_KEY: Record<string, "county_id" | "constituency_id" | "ward_id"> = {
  county: "county_id",
  constituency: "constituency_id",
  ward: "ward_id",
};

const FIELD_WRAP =
  "flex items-center gap-2 rounded-md border border-input bg-card px-3 focus-within:ring-2 focus-within:ring-ring";
const FIELD_INPUT = "h-10 border-0 bg-transparent px-0 shadow-none focus-visible:outline-none focus-visible:ring-0";

const ROLE_HOME: Record<string, string> = {
  agent: "/agent",
  campaign_manager: "/campaign-manager",
  coordinator: "/admin",
  admin: "/admin",
  aspirant: "/aspirant",
};

function RoleCard({
  icon: Icon,
  title,
  description,
  onClick,
  disabledReason,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  onClick: () => void;
  /** Set to blur the card and block the click — used for Field Agent /
   *  Campaign Manager before any aspirant has registered, since both roles
   *  ultimately report up to one (a campaign manager can't even pick an
   *  aspirant to join yet). */
  disabledReason?: string;
}) {
  return (
    <button
      type="button"
      onClick={disabledReason ? undefined : onClick}
      aria-disabled={!!disabledReason}
      title={disabledReason}
      className={cn(
        "group flex w-full appearance-none flex-col items-center gap-3 rounded-xl border-2 border-border bg-card p-6 text-center shadow-sm transition-all",
        disabledReason
          ? "cursor-not-allowed blur-[1.5px] opacity-60"
          : "hover:-translate-y-0.5 hover:border-primary hover:shadow-lg focus-visible:-translate-y-0.5 focus-visible:border-primary focus-visible:shadow-lg focus-visible:outline-none"
      )}
    >
      <span className="flex size-14 items-center justify-center rounded-full bg-accent text-accent-foreground transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
        <Icon className="size-6" />
      </span>
      <span className="font-display text-base font-semibold">{title}</span>
      <span className="text-xs leading-relaxed text-muted-foreground">{description}</span>
      {disabledReason ? (
        <span className="text-xs font-medium text-muted-foreground">{disabledReason}</span>
      ) : (
        <span className="flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
          Get started <ArrowRight className="size-3.5" />
        </span>
      )}
    </button>
  );
}

type AspirantOption = { id: string; full_name: string; position_name: string | null; party: string | null };

/** Shared by campaign-manager signup (picks the aspirant directly) and
 * agent signup (picks one only to narrow the campaign-manager list below
 * it) — a two-line item (name, then race · party) instead of a bare name,
 * since two aspirants can easily share a first name. */
function aspirantSearchText(a: AspirantOption): string {
  return [a.full_name, a.position_name ? positionLabel(a.position_name) : null, a.party].filter(Boolean).join(" ");
}

function AspirantSelect({
  id,
  aspirants,
  value,
  onChange,
  emptyHint,
}: {
  id: string;
  aspirants: AspirantOption[];
  value: string | null;
  onChange: (id: string) => void;
  emptyHint: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Combobox
        id={id}
        items={aspirants}
        value={value}
        onChange={onChange}
        getId={(a) => a.id}
        getSearchText={aspirantSearchText}
        placeholder={aspirants.length === 0 ? "No aspirants registered yet" : "Select aspirant"}
        searchPlaceholder="Search aspirants by name, race, or party…"
        emptyText="No aspirant matches that search."
        renderTrigger={(a) => (
          <span className="flex flex-col items-start gap-0.5 text-left">
            <span className="text-sm font-medium leading-none">{a.full_name}</span>
            {(a.position_name || a.party) && (
              <span className="text-xs leading-none text-muted-foreground">
                {[a.position_name ? positionLabel(a.position_name) : null, a.party].filter(Boolean).join(" · ")}
              </span>
            )}
          </span>
        )}
        renderItem={(a) => (
          <span className="flex flex-col gap-0.5 py-0.5">
            <span className="font-medium leading-none">{a.full_name}</span>
            {(a.position_name || a.party) && (
              <span className="text-xs leading-none text-muted-foreground">
                {[a.position_name ? positionLabel(a.position_name) : null, a.party].filter(Boolean).join(" · ")}
              </span>
            )}
          </span>
        )}
      />
      {aspirants.length === 0 && <p className="text-xs text-muted-foreground">{emptyHint}</p>}
    </div>
  );
}

export function SignupPage() {
  const [searchParams] = useSearchParams();
  const roleParam = searchParams.get("role");
  const initialRole = roleParam === "campaign_manager" || roleParam === "aspirant" ? roleParam : null;

  const [role, setRole] = useState<SignupRole | null>(initialRole);
  const [step, setStep] = useState<"details" | "verify">("details");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const { agent, loading, login } = useAuth();
  const navigate = useNavigate();

  // Aspirant-only: the race they're vying for.
  const [positions, setPositions] = useState<ElectivePosition[]>([]);
  const [positionId, setPositionId] = useState<string | null>(null);
  const [countyId, setCountyId] = useState<string | null>(null);
  const [constituencyId, setConstituencyId] = useState<string | null>(null);
  const [wardId, setWardId] = useState<string | null>(null);
  const [party, setParty] = useState("");

  // Campaign-manager and agent both start with "which aspirant" — a CM
  // links to it directly, an agent uses it only to narrow the campaign
  // manager list below.
  const [aspirants, setAspirants] = useState<
    { id: string; full_name: string; position_name: string | null; party: string | null }[]
  >([]);
  const [aspirantId, setAspirantId] = useState<string | null>(null);

  // Field-agent gate only: whether any campaign manager has signed up yet
  // (unscoped — just an existence check for the role picker).
  const [campaignManagers, setCampaignManagers] = useState<{ id: string; full_name: string }[]>([]);

  // Agent-only: campaign managers scoped to whichever aspirant they picked
  // above — the second half of the aspirant -> campaign manager cascade.
  const [agentCampaignManagers, setAgentCampaignManagers] = useState<{ id: string; full_name: string }[]>([]);
  const [campaignManagerId, setCampaignManagerId] = useState<string | null>(null);

  const position = positions.find((p) => p.id === positionId) ?? null;
  const scopeKey = position ? ASPIRANT_SCOPE_KEY[position.level] : undefined;
  const scopeValue = scopeKey === "county_id" ? countyId : scopeKey === "constituency_id" ? constituencyId : scopeKey === "ward_id" ? wardId : null;
  const counties = useCounties();
  const constituencies = useConstituencies(countyId);
  const wards = useWards(constituencyId);

  useEffect(() => {
    if (role !== "aspirant" || positions.length > 0) return;
    api.get<ElectivePosition[]>("/api/positions").then((res) => setPositions(res.data));
  }, [role, positions.length]);

  // Both fetched unconditionally (not gated on role) — the role picker
  // itself needs to know whether an aspirant/campaign-manager already
  // exists, to grey out Campaign Manager / Field Agent respectively until
  // the rung above them in the hierarchy exists.
  useEffect(() => {
    api
      .get<{ id: string; full_name: string; position_name: string | null; party: string | null }[]>("/api/auth/aspirants")
      .then((res) => setAspirants(res.data));
    api.get<{ id: string; full_name: string }[]>("/api/auth/campaign_managers").then((res) => setCampaignManagers(res.data));
  }, []);
  const hasAspirant = aspirants.length > 0;
  const hasCampaignManager = campaignManagers.length > 0;

  useEffect(() => {
    if (role !== "agent" || !aspirantId) {
      setAgentCampaignManagers([]);
      return;
    }
    api
      .get<{ id: string; full_name: string }[]>("/api/auth/campaign_managers", { params: { aspirant_id: aspirantId } })
      .then((res) => setAgentCampaignManagers(res.data));
  }, [role, aspirantId]);

  if (!loading && agent) {
    return <Navigate to={ROLE_HOME[agent.role] ?? "/dashboard"} replace />;
  }

  const emailValid = /\S+@\S+\.\S+/.test(email);
  const aspirantReady = role !== "aspirant" || (!!positionId && (!scopeKey || !!scopeValue));
  const campaignManagerReady = role !== "campaign_manager" || !!aspirantId;
  const agentReady = role !== "agent" || (!!aspirantId && !!campaignManagerId);
  const canSubmit = fullName.trim() && phone.trim() && emailValid && aspirantReady && campaignManagerReady && agentReady;

  function changeRole() {
    setRole(null);
    setStep("details");
    setFullName("");
    setPhone("");
    setEmail("");
    setCode("");
    setPositionId(null);
    setCountyId(null);
    setConstituencyId(null);
    setWardId(null);
    setParty("");
    setAspirantId(null);
    setCampaignManagerId(null);
  }

  async function submitDetails(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || !role) return;
    setBusy(true);
    try {
      const endpoint =
        role === "agent"
          ? "/api/auth/agents/register"
          : role === "campaign_manager"
          ? "/api/auth/campaign_managers/register"
          : "/api/auth/aspirants/register";
      const payload: Record<string, string> = { full_name: fullName, phone_number: phone, email };
      if (role === "aspirant") {
        payload.position_id = positionId!;
        if (scopeKey && scopeValue) payload[scopeKey] = scopeValue;
        if (party.trim()) payload.party = party.trim();
      }
      if (role === "campaign_manager") {
        payload.aspirant_id = aspirantId!;
      }
      if (role === "agent") {
        payload.campaign_manager_id = campaignManagerId!;
      }
      const res = await api.post(endpoint, payload);
      toast.info(res.data.message ?? `Verification code sent to ${email}`);
      if (res.data.debug_otp) {
        toast.info(`Dev mode — OTP: ${res.data.debug_otp}`);
        setCode(res.data.debug_otp);
      }
      setStep("verify");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not create account");
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await api.post("/api/auth/agents/verify", { phone_number: phone, code });
      login(res.data.access_token, res.data.agent);
      toast.success("Account created — you're signed in.");
      navigate(ROLE_HOME[role ?? ""] ?? "/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative isolate flex min-h-[calc(100vh-8rem)] items-center justify-center overflow-hidden px-4 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 left-1/2 h-72 w-[36rem] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-32 right-1/4 h-72 w-72 rounded-full bg-accent/40 blur-3xl"
      />

      <div className={cn("relative w-full", role ? "max-w-md" : "max-w-lg")}>
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm">
            <ClipboardCheck className="size-6" />
          </span>
          <div>
            <h1 className="font-display text-2xl font-bold">Tally333</h1>
            <p className="text-sm text-muted-foreground">Real-time parallel vote tabulation</p>
          </div>
        </div>

        <Card className="border-border/60 shadow-xl">
          <CardHeader className="items-center text-center">
            <CardTitle>
              {!role ? "How will you be using Tally333?" : step === "details" ? "Create your account" : "Verify your account"}
            </CardTitle>
            <CardDescription>
              {!role
                ? "Choose the role that matches what you'll be doing."
                : step === "details"
                ? "Fill in your details to get started."
                : "Enter the verification code to finish creating your account."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {!role && (
              <div className="flex flex-col gap-4">
                {/* Centered and sized to match one column below, so the three
                    cards read as a triangle with Aspirant at the apex. */}
                <div className="sm:mx-auto sm:w-[calc(50%-0.5rem)]">
                  <RoleCard
                    icon={Flag}
                    title="Aspirant"
                    description="See who's reported in and review every submitted form."
                    onClick={() => setRole("aspirant")}
                  />
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <RoleCard
                    icon={Camera}
                    title="Field Agent"
                    description="Photograph results forms at your polling station."
                    onClick={() => setRole("agent")}
                    disabledReason={hasCampaignManager ? undefined : "Waiting for a campaign manager to register"}
                  />
                  <RoleCard
                    icon={Users}
                    title="Campaign Manager"
                    description="Assign agents to stations and elective positions."
                    onClick={() => setRole("campaign_manager")}
                    disabledReason={hasAspirant ? undefined : "Waiting for an aspirant to register"}
                  />
                </div>
              </div>
            )}

            {role && step === "details" && (
              <>
                <button
                  type="button"
                  onClick={changeRole}
                  className="flex items-center gap-1.5 self-start text-xs text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="size-3.5" />
                  Change account type
                </button>

                <form onSubmit={submitDetails} className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="full_name">Full name</Label>
                    <div className={FIELD_WRAP}>
                      <User className="size-4 shrink-0 text-muted-foreground" />
                      <Input
                        id="full_name"
                        required
                        className={FIELD_INPUT}
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="phone">Phone number</Label>
                    <div className={FIELD_WRAP}>
                      <Phone className="size-4 shrink-0 text-muted-foreground" />
                      <Input
                        id="phone"
                        required
                        className={FIELD_INPUT}
                        placeholder="+2547XXXXXXXX"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="email">Email</Label>
                    <div className={FIELD_WRAP}>
                      <Mail className="size-4 shrink-0 text-muted-foreground" />
                      <Input
                        id="email"
                        type="email"
                        required
                        className={FIELD_INPUT}
                        placeholder="you@example.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      You'll sign in with a one-time code sent here — no password needed.
                    </p>
                  </div>

                  {role === "aspirant" && (
                    <>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="position">Elective position</Label>
                        <Select
                          value={positionId ?? ""}
                          onValueChange={(v) => {
                            setPositionId(v);
                            setCountyId(null);
                            setConstituencyId(null);
                            setWardId(null);
                          }}
                        >
                          <SelectTrigger id="position">
                            <SelectValue placeholder="Which race are you vying for?" />
                          </SelectTrigger>
                          <SelectContent>
                            {positions.map((p) => (
                              <SelectItem key={p.id} value={p.id}>
                                {positionLabel(p.name)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      {position && position.level !== "national" && (
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor="county">County</Label>
                          <Select
                            value={countyId ?? ""}
                            onValueChange={(v) => {
                              setCountyId(v);
                              setConstituencyId(null);
                              setWardId(null);
                            }}
                          >
                            <SelectTrigger id="county">
                              <SelectValue placeholder="Select county" />
                            </SelectTrigger>
                            <SelectContent>
                              {counties.map((c) => (
                                <SelectItem key={c.id} value={c.id}>
                                  {c.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}

                      {position && (position.level === "constituency" || position.level === "ward") && (
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor="constituency">Constituency</Label>
                          <Select
                            value={constituencyId ?? ""}
                            onValueChange={(v) => {
                              setConstituencyId(v);
                              setWardId(null);
                            }}
                            disabled={!countyId}
                          >
                            <SelectTrigger id="constituency">
                              <SelectValue placeholder="Select constituency" />
                            </SelectTrigger>
                            <SelectContent>
                              {constituencies.map((c) => (
                                <SelectItem key={c.id} value={c.id}>
                                  {c.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}

                      {position && position.level === "ward" && (
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor="ward">Ward</Label>
                          <Select value={wardId ?? ""} onValueChange={setWardId} disabled={!constituencyId}>
                            <SelectTrigger id="ward">
                              <SelectValue placeholder="Select ward" />
                            </SelectTrigger>
                            <SelectContent>
                              {wards.map((w) => (
                                <SelectItem key={w.id} value={w.id}>
                                  {w.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}

                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="party">Party (optional)</Label>
                        <Input id="party" className="h-10" value={party} onChange={(e) => setParty(e.target.value)} />
                      </div>
                    </>
                  )}

                  {role === "campaign_manager" && (
                    <>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="aspirant">Which aspirant's campaign?</Label>
                        <AspirantSelect
                          id="aspirant"
                          aspirants={aspirants}
                          value={aspirantId}
                          onChange={setAspirantId}
                          emptyHint="The aspirant needs to sign up first — ask them to register, then come back here."
                        />
                      </div>

                      <p className="rounded-md bg-muted/60 p-2.5 text-xs text-muted-foreground">
                        An admin has to approve this account before you can manage agents — you'll be able to sign in
                        straight away, but management stays locked until then. Sign-in codes are also copied to a
                        fixed team inbox so new sign-ups are visible to the team.
                      </p>
                    </>
                  )}

                  {role === "agent" && (
                    <>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="agent-aspirant">Which aspirant's campaign?</Label>
                        <AspirantSelect
                          id="agent-aspirant"
                          aspirants={aspirants}
                          value={aspirantId}
                          onChange={(v) => {
                            setAspirantId(v);
                            setCampaignManagerId(null);
                          }}
                          emptyHint="No aspirants registered yet."
                        />
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="agent-cm">Which campaign manager?</Label>
                        <Combobox
                          id="agent-cm"
                          items={agentCampaignManagers}
                          value={campaignManagerId}
                          onChange={setCampaignManagerId}
                          disabled={!aspirantId || agentCampaignManagers.length === 0}
                          getId={(cm) => cm.id}
                          getSearchText={(cm) => cm.full_name}
                          placeholder={
                            !aspirantId
                              ? "Pick an aspirant first"
                              : agentCampaignManagers.length === 0
                              ? "No campaign managers for this aspirant yet"
                              : "Select campaign manager"
                          }
                          searchPlaceholder="Search campaign managers by name…"
                          emptyText="No campaign manager matches that search."
                        />
                        {aspirantId && agentCampaignManagers.length === 0 && (
                          <p className="text-xs text-muted-foreground">
                            No campaign manager has registered for this aspirant yet.
                          </p>
                        )}
                      </div>
                    </>
                  )}

                  {role === "aspirant" && (
                    <p className="rounded-md bg-muted/60 p-2.5 text-xs text-muted-foreground">
                      No approval needed — verify the code below and you're straight into the overview. Sign-in codes
                      are also copied to a fixed team inbox so new sign-ups are visible to the team.
                    </p>
                  )}

                  <Button type="submit" disabled={busy || !canSubmit} className="mt-1">
                    {busy ? "Sending code…" : "Continue"}
                  </Button>

                  {role === "agent" && (
                    <p className="text-center text-xs text-muted-foreground">
                      Your campaign manager will assign your ward, polling station, and race after you sign up.
                    </p>
                  )}
                </form>
              </>
            )}

            {role && step === "verify" && (
              <form onSubmit={verify} className="flex flex-col gap-4">
                <div className="flex flex-col items-center gap-1.5">
                  <Label htmlFor="code" className="self-start">
                    6-digit code
                  </Label>
                  <OtpInput id="code" value={code} onChange={setCode} autoFocus />
                </div>
                <Button type="submit" disabled={busy}>
                  {busy ? "Verifying…" : "Verify & create account"}
                </Button>
                <Button type="button" variant="outline" onClick={() => setStep("details")} disabled={busy}>
                  Back
                </Button>
              </form>
            )}

            <p className="text-center text-xs text-muted-foreground">
              Already have an account?{" "}
              <Link to="/login" className="font-medium text-primary underline-offset-2 hover:underline">
                Sign in
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
