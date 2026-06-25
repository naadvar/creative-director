import { Link } from 'react-router-dom'

const CONTACT = 'naadvar@gmail.com' // TODO: swap for a dedicated support address before launch

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-muted">{children}</div>
    </section>
  )
}

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 py-2">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Privacy Policy</h1>
        <p className="mt-1 text-xs text-muted">Last updated: June 2026</p>
      </div>

      <p className="text-sm leading-relaxed text-muted">
        Creative Director is a craft-feedback tool for short-form video. This policy explains what
        we collect, why, and your choices. We keep it short because we keep the data minimal.
      </p>

      <Section title="What we collect">
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <span className="text-text/80">Your email</span> — to sign you in (passwordless, no
            password stored) and to save your reads to your account.
          </li>
          <li>
            <span className="text-text/80">Videos you upload</span> — the reels you choose to
            analyze, plus any caption you add.
          </li>
          <li>
            <span className="text-text/80">Your reads</span> — the craft analysis we generate for
            each reel, so your history and your Creator DNA persist.
          </li>
          <li>
            <span className="text-text/80">Basic usage</span> — e.g. which notes you mark helpful,
            used only to improve the analysis.
          </li>
        </ul>
        <p>We do not collect contacts, location, or device identifiers for advertising.</p>
      </Section>

      <Section title="How we use it">
        <p>
          Your uploaded video is processed to generate its craft read — this involves sending the
          video and its derived data to our AI analysis provider for that purpose only. We use your
          reads to build your personal Creator DNA and, if you opt in, to email you when a read is
          ready. We do not sell your data or use your videos to train third-party models.
        </p>
      </Section>

      <Section title="Who processes it">
        <p>
          We use service providers strictly to run the product: cloud hosting and storage, and an
          AI model provider that performs the video analysis. They process your data on our behalf
          under their own security terms. Your uploads are private to your account and are not
          shown to other users.
        </p>
      </Section>

      <Section title="Retention & your choices">
        <p>
          We keep your account and reads until you ask us to delete them. You can request deletion
          of your account, your uploads, or your reads at any time by emailing us. Deleting your
          account removes your email, your uploaded videos, and your reads.
        </p>
      </Section>

      <Section title="Contact">
        <p>
          Questions or a deletion request? Email{' '}
          <a href={`mailto:${CONTACT}`} className="text-accent hover:underline">
            {CONTACT}
          </a>
          .
        </p>
      </Section>

      <div className="border-t border-border pt-4">
        <Link to="/" className="text-sm text-accent hover:underline">
          ← Back to Creative Director
        </Link>
      </div>
    </div>
  )
}
