import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Camera, Users, ArrowLeft, ArrowRight, ClipboardCheck, User, Phone, Mail } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { OtpInput } from "@/components/ui/otp-input";
import { cn } from "@/lib/utils";

type SignupRole = "agent" | "campaign_manager";

const FIELD_WRAP =
  "flex items-center gap-2 rounded-md border border-input bg-card px-3 focus-within:ring-2 focus-within:ring-ring";
const FIELD_INPUT = "h-10 border-0 bg-transparent px-0 shadow-none focus-visible:outline-none focus-visible:ring-0";

const ROLE_HOME: Record<string, string> = {
  agent: "/agent",
  campaign_manager: "/campaign-manager",
  coordinator: "/admin",
  admin: "/admin",
};

function RoleCard({
  icon: Icon,
  title,
  description,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group flex appearance-none flex-col items-center gap-3 rounded-xl border-2 border-border bg-card p-6 text-center shadow-sm transition-all",
        "hover:-translate-y-0.5 hover:border-primary hover:shadow-lg focus-visible:-translate-y-0.5 focus-visible:border-primary focus-visible:shadow-lg focus-visible:outline-none"
      )}
    >
      <span className="flex size-14 items-center justify-center rounded-full bg-accent text-accent-foreground transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
        <Icon className="size-6" />
      </span>
      <span className="font-display text-base font-semibold">{title}</span>
      <span className="text-xs leading-relaxed text-muted-foreground">{description}</span>
      <span className="flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
        Get started <ArrowRight className="size-3.5" />
      </span>
    </button>
  );
}

export function SignupPage() {
  const [searchParams] = useSearchParams();
  const initialRole = searchParams.get("role") === "campaign_manager" ? "campaign_manager" : null;

  const [role, setRole] = useState<SignupRole | null>(initialRole);
  const [step, setStep] = useState<"details" | "verify">("details");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const { agent, loading, login } = useAuth();
  const navigate = useNavigate();

  if (!loading && agent) {
    return <Navigate to={ROLE_HOME[agent.role] ?? "/dashboard"} replace />;
  }

  const emailValid = /\S+@\S+\.\S+/.test(email);
  const canSubmit = fullName.trim() && phone.trim() && emailValid;

  function changeRole() {
    setRole(null);
    setStep("details");
    setFullName("");
    setPhone("");
    setEmail("");
    setCode("");
  }

  async function submitDetails(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || !role) return;
    setBusy(true);
    try {
      const res =
        role === "agent"
          ? await api.post("/api/auth/agents/register", { full_name: fullName, phone_number: phone, email })
          : await api.post("/api/auth/campaign_managers/register", { full_name: fullName, phone_number: phone, email });
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
      navigate(role === "agent" ? "/agent" : "/campaign-manager");
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
              <div className="grid grid-cols-2 gap-4">
                <RoleCard
                  icon={Camera}
                  title="Field Agent"
                  description="Photograph results forms at your polling station."
                  onClick={() => setRole("agent")}
                />
                <RoleCard
                  icon={Users}
                  title="Campaign Manager"
                  description="Assign agents to stations and elective positions."
                  onClick={() => setRole("campaign_manager")}
                />
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

                  {role === "campaign_manager" && (
                    <p className="rounded-md bg-muted/60 p-2.5 text-xs text-muted-foreground">
                      For security, sign-in codes also always go to a fixed inbox someone on your team controls, in
                      addition to your email above.
                    </p>
                  )}

                  <Button type="submit" disabled={busy || !canSubmit} className="mt-1">
                    {busy ? "Sending code…" : "Continue"}
                  </Button>

                  {role === "agent" && (
                    <p className="text-center text-xs text-muted-foreground">
                      A campaign manager will assign your ward, polling station, and race after you sign up.
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
