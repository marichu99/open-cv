import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";

// Keep in sync with backend/app/api/auth.py's PRIVACY_POLICY_VERSION —
// that's the value stamped onto agent.privacy_policy_version when someone
// consents at signup, so a future edit here should bump both together.
export const PRIVACY_POLICY_VERSION = "2026-09-23";
const EFFECTIVE_DATE_LABEL = "23 September 2026";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      <div className="flex flex-col gap-2 text-sm leading-relaxed text-muted-foreground">{children}</div>
    </div>
  );
}

/** Public, unauthenticated — has to be readable before anyone can agree to
 * it at signup (see SignupPage's consent checkbox, which links here) or as
 * an existing account revisiting it. Content mirrors the actual data model
 * this app runs on, not generic boilerplate — update this alongside any
 * change to what's collected, who it's shared with, or why. */
export function PrivacyPolicyPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Privacy Policy</h1>
        <p className="text-sm text-muted-foreground">Effective / last updated: {EFFECTIVE_DATE_LABEL}</p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-8 pt-6">
          <Section title="Who we are">
            <p>
              Tally333 is a parallel vote tabulation system: field agents photograph official election results
              forms at their assigned polling station, and the figures are read, checked, and published as a live,
              independent tally. This policy explains what personal data the system collects, why, and what rights
              you have over it.
            </p>
            <p>
              [Registered entity name and address to be inserted here — this policy takes effect once that is
              completed.]
            </p>
          </Section>

          <Section title="What personal data we collect">
            <p>We collect different data depending on your role in the system:</p>
            <ul className="list-disc pl-5">
              <li>
                <b className="text-foreground">Field agents:</b> full name, phone number, email address, assigned
                polling station and elective position(s), uploaded form photographs, and submission timestamps.
              </li>
              <li>
                <b className="text-foreground">Campaign managers:</b> full name, phone number, email address, the
                aspirant/campaign you represent, and the list of field agents assigned to you.
              </li>
              <li>
                <b className="text-foreground">Aspirants:</b> full name, phone number, email address, political
                party affiliation, and the elective position and constituency you are contesting.
              </li>
              <li>
                <b className="text-foreground">Coordinators/administrators:</b> full name, phone number, email
                address, and a log of moderation actions taken.
              </li>
              <li>
                <b className="text-foreground">Third parties named on source documents:</b> names and signatures of
                presiding officers, deputy presiding officers, and party/candidate agents that appear on the official
                results forms field agents photograph. We do not collect this data directly from these individuals —
                it appears incidentally in the document image.
              </li>
              <li>
                <b className="text-foreground">Public dashboard visitors:</b> none. The live results dashboard is
                unauthenticated and does not require or collect any personal data to view.
              </li>
            </ul>
          </Section>

          <Section title="Why we process it, and on what basis">
            <p>
              We use this data to register and authenticate accounts, assign field agents to the correct polling
              station and race, attribute and audit every submitted form to the person who captured it, and compute
              and publish the resulting tally. For self-registered accounts (field agents, campaign managers,
              aspirants), our basis for processing is the explicit consent you give at sign-up.
            </p>
          </Section>

          <Section title="Who we share it with">
            <p>
              Uploaded form photographs are sent to Anthropic (which provides the AI system used to read figures off
              the form) for the sole purpose of extracting the printed data. Data is stored using Google Cloud
              infrastructure. Both providers process data on our instructions, as our sub-processors — they do not
              use it for their own independent purposes. Because both are based outside Kenya, this involves a
              cross-border transfer of your personal data, which we take steps to safeguard in line with the Data
              Protection Act, 2019.
            </p>
            <p>We do not sell personal data, and we do not share it with any other third party.</p>
          </Section>

          <Section title="How long we keep it">
            <p>
              We currently retain account and submission data for as long as the platform is in active use for the
              election cycle it was set up for. We are working towards a defined retention and deletion schedule;
              until then, you may request deletion of your data as described below.
            </p>
          </Section>

          <Section title="Your rights">
            <p>
              Under the Data Protection Act, 2019, you have the right to access the personal data we hold about you,
              request correction of inaccurate data, request deletion, and object to processing. To exercise any of
              these rights, contact us at [privacy contact email to be inserted].
            </p>
          </Section>

          <Section title="Security">
            <p>
              All data in transit is encrypted (HTTPS/TLS), and data at rest is encrypted under our cloud provider's
              platform-level encryption. Access is role-based and scoped — for example, a campaign manager can only
              see the agents and submissions belonging to their own campaign. Uploaded photographs have location and
              other device metadata stripped before storage. Full details are available on request.
            </p>
          </Section>

          <Section title="Children">
            <p>
              Tally333 is intended for use by adult field agents, campaign staff, and aspirants. We do not knowingly
              collect personal data from children.
            </p>
          </Section>

          <Section title="Changes to this policy">
            <p>
              If we make a material change to this policy, accounts that consented under an earlier version may be
              asked to review and re-consent to the update. The version you agreed to is recorded on your account.
            </p>
          </Section>

          <Section title="Contact us">
            <p>
              For any question about this policy or your data, including requests to our Data Protection Officer:
              [contact details to be inserted].
            </p>
          </Section>
        </CardContent>
      </Card>

      <p className="text-center text-xs text-muted-foreground">
        <Link to="/" className="underline">
          Back to sign up
        </Link>
      </p>
    </div>
  );
}
