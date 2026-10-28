import { Github, Linkedin, Mail, Phone } from "lucide-react"
import { type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { trackEvent } from "@/lib/analytics"
import { READ_RAILS } from "./rails"

/**
 * Who made Majlisna: the maker's portrait, name, role and bio, his links, then his
 * experience, education, skills and the free mentoring offer. The content and links are
 * the ones the page always had; the frame is the Samar one (hairline lists, one brass
 * panel for the invitation, 44 px contact buttons). No ring animation, no hover lift.
 */
const EMAIL = "souhib.t@icloud.com"
const PHONE_HREF = "tel:+33643142020"
const PHONE_SHOWN = "+33 6 43 14 20 20"

const EXPERIENCE = ["experienceMadura", "experienceSnap", "experienceEnedis", "experienceBnp", "experienceCloudeasier"] as const
const EDUCATION = ["educationEpitech", "educationSfsu"] as const

const SKILLS = [
  "Python",
  "FastAPI",
  "Flask",
  "React",
  "TypeScript",
  "PostgreSQL",
  "MySQL",
  "AWS",
  "GCP",
  "Docker",
  "Terraform",
  "Ansible",
  "Gitlab CI/CD",
  "Traefik",
  "Prefect",
  "SQLModel",
  "Tailwind CSS",
  "OpenCV",
  "Pandas",
  "NumPy",
  "Scikit-learn",
]

/** A sub-section on the page's two rails: its title on the start rail, its list after. */
function RailRow({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div className={READ_RAILS}>
      <h3 className="type-title text-[24px] md:pt-3">{title}</h3>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

export function MakerSection() {
  const { t } = useTranslation()

  const contacts = [
    { href: `mailto:${EMAIL}`, icon: Mail, label: t("about.contactEmail"), platform: "email" },
    { href: PHONE_HREF, icon: Phone, label: t("about.contactPhone"), platform: "phone" },
    { href: "https://www.linkedin.com/in/souhib-trabelsi/", icon: Linkedin, label: "LinkedIn", platform: "linkedin" },
    { href: "https://github.com/Souhib", icon: Github, label: "GitHub", platform: "github" },
  ]

  return (
    <section id="maker" aria-labelledby="maker-title" className="grid scroll-mt-[calc(var(--navh)+24px)] gap-[clamp(40px,5vw,64px)]">
      {/* who */}
      <div className={READ_RAILS}>
        <h2 id="maker-title" className="type-h3">
          {t("about.makerTitle")}
        </h2>
        <div className="grid min-w-0 gap-5">
          <div className="flex items-center gap-5">
            <img
              src="/souhib.jpeg"
              alt={t("about.portraitAlt")}
              width={600}
              height={828}
              decoding="async"
              className="size-24 shrink-0 rounded-full border border-line object-cover object-[50%_22%] outline-[1.5px] outline-offset-[3px] outline-line-brass-strong sm:size-28"
            />
            <div className="grid min-w-0 gap-1">
              <h3 className="type-title">{t("about.name")}</h3>
              <p className="text-[15px] text-muted-foreground">{t("about.role")}</p>
            </div>
          </div>
          <p className="type-body max-w-[54ch] text-pretty">{t("about.bio")}</p>
          <div className="grid gap-3">
            <h4 className="type-label">{t("about.contactMe")}</h4>
            <ul className="flex flex-wrap gap-2.5">
              {contacts.map((c) => {
                const external = c.href.startsWith("http")
                return (
                  <li key={c.platform}>
                    <Button asChild variant="secondary" size="sm" className="h-11" iconStart={<c.icon aria-hidden="true" />}>
                      <a
                        href={c.href}
                        target={external ? "_blank" : undefined}
                        rel={external ? "noopener noreferrer" : undefined}
                        onClick={() => trackEvent("social-click", { platform: c.platform })}
                      >
                        <span lang={external ? "en" : undefined}>{c.label}</span>
                        {external ? <span className="sr-only">{t("ui.opensInNewTab")}</span> : null}
                      </a>
                    </Button>
                  </li>
                )
              })}
            </ul>
          </div>
        </div>
      </div>

      <RailRow title={t("about.experience")}>
        <ol className="border-b border-line">
          {EXPERIENCE.map((key) => (
            <li key={key} className="grid gap-1 border-t border-line py-4">
              <p className="text-[16px] leading-snug font-medium">
                <bdi>{t(`about.${key}Title`)}</bdi>
              </p>
              <p className="num text-[13.5px] text-muted-foreground">{t(`about.${key}Period`)}</p>
              <p className="mt-1.5 max-w-[60ch] text-[15.5px] leading-relaxed text-pretty text-muted-foreground">{t(`about.${key}Desc`)}</p>
            </li>
          ))}
        </ol>
      </RailRow>

      <RailRow title={t("about.education")}>
        <ul className="border-b border-line">
          {EDUCATION.map((key) => (
            <li key={key} className="border-t border-line py-3.5 text-[16px] leading-snug">
              <bdi>{t(`about.${key}`)}</bdi>
            </li>
          ))}
        </ul>
      </RailRow>

      {/* skills: a line of lozenge bullets, not a wall of chips */}
      <RailRow title={t("about.skills")}>
        <ul lang="en" className="flex flex-wrap items-center gap-x-5 gap-y-2.5 border-t border-line pt-4 text-[15.5px]">
          {SKILLS.map((skill) => (
            <li key={skill} className="inline-flex items-center gap-2">
              <Lozenge size={5} />
              <bdi>{skill}</bdi>
            </li>
          ))}
        </ul>
      </RailRow>

      {/* free mentoring: the one invitation, so the one brass panel */}
      <div className={READ_RAILS}>
        <Panel tone="brass" aria-labelledby="mentoring-title" className="grid gap-4 md:col-start-2">
          <h3 id="mentoring-title" className="type-title text-[24px]">
            {t("about.mentoringTitle")}
          </h3>
          <p className="max-w-[58ch] text-[16px] leading-relaxed text-pretty">{t("about.mentoringText")}</p>
          <div className="flex flex-wrap gap-2.5 pt-1">
            <Button asChild iconStart={<Mail aria-hidden="true" />}>
              <a href={`mailto:${EMAIL}`}>
                <span dir="ltr" className="bidi-isolate">
                  {EMAIL}
                </span>
              </a>
            </Button>
            <Button asChild variant="secondary" iconStart={<Phone aria-hidden="true" />}>
              <a href={PHONE_HREF}>
                <span dir="ltr" className="num bidi-isolate">
                  {PHONE_SHOWN}
                </span>
              </a>
            </Button>
          </div>
        </Panel>
      </div>
    </section>
  )
}
