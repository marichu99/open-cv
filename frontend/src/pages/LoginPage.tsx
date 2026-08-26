import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { User } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { OtpInput } from "@/components/ui/otp-input";

const FIELD_WRAP = "flex items-center gap-2 rounded-md border border-input bg-card px-3 focus-within:ring-2 focus-within:ring-ring";
const FIELD_INPUT = "h-10 border-0 bg-transparent px-0 shadow-none focus-visible:outline-none focus-visible:ring-0";

const ROLE_HOME: Record<string, string> = {
  agent: "/agent",
  campaign_manager: "/campaign-manager",
  coordinator: "/admin",
  admin: "/admin",
  viewer: "/dashboard",
};

export function LoginPage() {
  const [step, setStep] = useState<"request" | "verify">("request");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function requestCode(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await api.post("/api/auth/agents/otp/request", { phone_number: phoneNumber });
      toast.info(res.data.message ?? "Verification code sent.");
      if (res.data.debug_otp) {
        toast.info(`Dev mode — OTP: ${res.data.debug_otp}`);
        setCode(res.data.debug_otp);
      }
      setStep("verify");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not send code");
    } finally {
      setSubmitting(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await api.post("/api/auth/agents/verify", { phone_number: phoneNumber, code });
      login(res.data.access_token, res.data.agent);
      toast.success(`Signed in as ${res.data.agent.full_name}`);
      navigate(ROLE_HOME[res.data.agent.role as string] ?? "/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <Card>
        <CardHeader className="items-center text-center">
          <CardTitle>Tally333</CardTitle>
          <CardDescription>
            {step === "request" ? "Sign in with a one-time code" : "Enter the code we sent you"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {step === "request" ? (
            <form onSubmit={requestCode} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="phone">Phone number</Label>
                <div className={FIELD_WRAP}>
                  <User className="size-4 shrink-0 text-muted-foreground" />
                  <Input
                    id="phone"
                    required
                    className={FIELD_INPUT}
                    placeholder="+2547XXXXXXXX"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    autoComplete="username"
                  />
                </div>
              </div>
              <Button type="submit" disabled={submitting} className="mt-1">
                {submitting ? "Sending…" : "Send code"}
              </Button>

              <p className="text-center text-sm text-muted-foreground">
                Don't have an account?{" "}
                <Link to="/" className="font-medium text-primary underline-offset-2 hover:underline">
                  Create one
                </Link>
              </p>
              <Link to="/" className="text-center text-xs text-muted-foreground hover:text-foreground">
                ← Back to home
              </Link>
            </form>
          ) : (
            <form onSubmit={verify} className="flex flex-col gap-4">
              <div className="flex flex-col items-center gap-1.5">
                <Label htmlFor="code" className="self-start">
                  6-digit code
                </Label>
                <OtpInput id="code" value={code} onChange={setCode} autoFocus />
              </div>
              <Button type="submit" disabled={submitting} className="mt-1">
                {submitting ? "Verifying…" : "Verify & sign in"}
              </Button>
              <Button type="button" variant="outline" onClick={() => setStep("request")} disabled={submitting}>
                Back
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
