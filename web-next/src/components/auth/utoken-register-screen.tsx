"use client"

import { useEffect, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import { apiClient } from "@/lib/api"
import { AuthShell } from "./auth-shell"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

type Config = {
  enabled: boolean
  emailVerification: boolean
  phoneVerification: boolean
  turnstileSiteKey: string | null
  agreementUrl: string | null
  privacyUrl: string | null
}
type CaptchaWindow = Window & {
  turnstile?: {
    render: (container: HTMLElement, options: Record<string, unknown>) => string
    remove: (id: string) => void
    reset: (id: string) => void
  }
}

/** Render the upstream's public captcha; the token service performs the verification. */
function RegistrationCaptcha({
  siteKey,
  version,
  onToken,
}: {
  siteKey: string
  version: number
  onToken: (value: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const widgetRef = useRef<string | undefined>(undefined)
  useEffect(() => {
    let widget: string | undefined
    let active = true
    const win = window as CaptchaWindow
    const mount = () => {
      if (
        !active ||
        !container.current ||
        widget !== undefined ||
        !win.turnstile
      )
        return
      widget = win.turnstile.render(container.current, {
        sitekey: siteKey,
        callback: onToken,
        "expired-callback": () => onToken(""),
        "error-callback": () => onToken(""),
      })
      widgetRef.current = widget
    }
    let script = document.getElementById(
      "utoken-turnstile",
    ) as HTMLScriptElement | null
    if (!script) {
      script = document.createElement("script")
      script.id = "utoken-turnstile"
      script.src =
        "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
      script.async = true
      document.head.appendChild(script)
    }
    script.addEventListener("load", mount)
    mount()
    return () => {
      active = false
      script?.removeEventListener("load", mount)
      if (widget !== undefined) win.turnstile?.remove(widget)
      widgetRef.current = undefined
    }
  }, [siteKey, onToken])
  useEffect(() => {
    if (version > 0 && widgetRef.current !== undefined) {
      ;(window as CaptchaWindow).turnstile?.reset(widgetRef.current)
    }
  }, [version])
  return <div ref={container} className="min-h-20" />
}

/** Same-page registration UI; token owns account creation, codes, delivery and policy enforcement. */
export function UtokenRegisterScreen({
  onBack,
}: {
  onBack: (registered?: boolean) => void
}) {
  const t = useTranslations("auth.tokenRegister")
  const [config, setConfig] = useState<Config | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [sendingCode, setSendingCode] = useState(false)
  const inFlight = useRef(false)
  const [method, setMethod] = useState("email")
  const [username, setUsername] = useState("")
  const [recipient, setRecipient] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [code, setCode] = useState("")
  const [agreed, setAgreed] = useState(false)
  const [captcha, setCaptcha] = useState("")
  const [captchaVersion, setCaptchaVersion] = useState(0)
  const [seconds, setSeconds] = useState(0)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setError("")
    apiClient
      .get<Config>("/auth/utoken/config", { auth: false, cache: "no-store" })
      .then((value) => {
        if (active) setConfig(value)
      })
      .catch((cause) => {
        if (active)
          setError(cause instanceof Error ? cause.message : t("unavailable"))
      })
    return () => {
      active = false
    }
  }, [reload, t])
  useEffect(() => {
    if (!seconds) return
    const timer = setTimeout(
      () => setSeconds((value) => Math.max(0, value - 1)),
      1000,
    )
    return () => clearTimeout(timer)
  }, [seconds])
  const needsCode = Boolean(
    config &&
    (method === "phone" ? config.phoneVerification : config.emailVerification),
  )
  const legal = Boolean(config?.agreementUrl || config?.privacyUrl)
  const captchaReady = !config?.turnstileSiteKey || Boolean(captcha)
  const recipientValid =
    method === "phone"
      ? /^\+?[\d ()-]{6,32}$/.test(recipient)
      : /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient)
  /** No retries for registration or delivery writes, avoiding duplicate accounts or messages. */
  async function perform(sendCode = false) {
    if (inFlight.current || !config?.enabled || (sendCode && seconds > 0))
      return
    setError("")
    if (!captchaReady) {
      setError(t("captchaRequired"))
      return
    }
    if ((sendCode || needsCode || recipient) && !recipientValid) {
      setError(t("invalidRecipient"))
      return
    }
    if (
      !sendCode &&
      (!username.trim() ||
        password.length < 8 ||
        password.length > 20 ||
        password !== confirm ||
        (needsCode && !code.trim()) ||
        (legal && !agreed))
    ) {
      setError(t("invalidForm"))
      return
    }
    inFlight.current = true
    // Keep editable fields mounted and enabled during delivery; blurring them collapses mobile keyboards.
    if (sendCode) {
      setSendingCode(true)
      setSeconds(60)
    } else setBusy(true)
    try {
      if (sendCode) {
        await apiClient.post(
          "/auth/utoken/code",
          { method, recipient, turnstile: captcha },
          { auth: false },
        )
        setSeconds(60)
      } else {
        await apiClient.post(
          "/auth/utoken/register",
          {
            username: username.trim(),
            password,
            email: method === "email" ? recipient : "",
            phone: method === "phone" ? recipient : "",
            verificationCode: code,
            agreed,
            turnstile: captcha,
          },
          { auth: false },
        )
        onBack(true)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("unavailable"))
    } finally {
      setBusy(false)
      setSendingCode(false)
      inFlight.current = false
      setCaptcha("")
      setCaptchaVersion((value) => value + 1)
    }
  }
  return (
    <AuthShell>
      <div className="mx-auto w-full max-w-sm">
        <h1 className="mb-2 text-center text-2xl font-bold">{t("title")}</h1>
        <p className="mb-6 text-center text-sm text-muted-foreground">
          {t("description")}
        </p>
        {!config && !error ? <p role="status">{t("loading")}</p> : null}
        {config?.enabled ? (
          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault()
              void perform()
            }}
          >
            <FieldGroup>
              {config.phoneVerification ? (
                <Tabs
                  value={method}
                  onValueChange={(value) => {
                    setMethod(value)
                    setRecipient("")
                    setCode("")
                  }}
                >
                  <TabsList>
                    <TabsTrigger disabled={busy} value="email">
                      {t("email")}
                    </TabsTrigger>
                    <TabsTrigger disabled={busy} value="phone">
                      {t("phone")}
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              ) : null}
              <Field>
                <FieldLabel htmlFor="token-register-username">
                  {t("username")}
                </FieldLabel>
                <Input
                  id="token-register-username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  maxLength={20}
                  autoComplete="username"
                  disabled={busy}
                  required
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="token-register-recipient">
                  {t(method === "phone" ? "phone" : "email")}
                  {needsCode ? " *" : ""}
                </FieldLabel>
                <Input
                  id="token-register-recipient"
                  type={method === "phone" ? "tel" : "email"}
                  value={recipient}
                  onChange={(event) => {
                    setRecipient(event.target.value)
                    setCode("")
                  }}
                  autoComplete={method === "phone" ? "tel" : "email"}
                  disabled={busy}
                />
              </Field>
              {needsCode ? (
                <Field>
                  <FieldLabel htmlFor="token-register-code">
                    {t("code")}
                  </FieldLabel>
                  <div className="flex gap-2">
                    <Input
                      id="token-register-code"
                      value={code}
                      onChange={(event) => setCode(event.target.value)}
                      autoComplete="one-time-code"
                      maxLength={32}
                      disabled={busy}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      disabled={
                        busy ||
                        sendingCode ||
                        seconds > 0 ||
                        !recipientValid ||
                        !captchaReady
                      }
                      onClick={() => void perform(true)}
                    >
                      {sendingCode
                        ? t("working")
                        : seconds
                          ? t("countdown", { seconds })
                          : t("sendCode")}
                    </Button>
                  </div>
                </Field>
              ) : null}
              <Field>
                <FieldLabel htmlFor="token-register-password">
                  {t("password")}
                </FieldLabel>
                <Input
                  id="token-register-password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={20}
                  disabled={busy}
                />
                <FieldDescription>{t("passwordHint")}</FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor="token-register-confirm">
                  {t("confirm")}
                </FieldLabel>
                <Input
                  id="token-register-confirm"
                  type="password"
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                  autoComplete="new-password"
                  disabled={busy}
                />
              </Field>
              {config.turnstileSiteKey ? (
                <Field>
                  <FieldLabel>{t("captcha")}</FieldLabel>
                  <RegistrationCaptcha
                    siteKey={config.turnstileSiteKey}
                    version={captchaVersion}
                    onToken={setCaptcha}
                  />
                  <FieldDescription>{t("captchaHint")}</FieldDescription>
                </Field>
              ) : null}
              {legal ? (
                <Field>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="token-register-agreed"
                      checked={agreed}
                      onCheckedChange={(value) => setAgreed(value === true)}
                      disabled={busy}
                    />
                    <FieldLabel htmlFor="token-register-agreed">
                      {t("agreed")}
                    </FieldLabel>
                  </div>
                  <div className="flex gap-3 text-sm">
                    {config.agreementUrl ? (
                      <a
                        href={config.agreementUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        {t("agreement")}
                      </a>
                    ) : null}
                    {config.privacyUrl ? (
                      <a
                        href={config.privacyUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        {t("privacy")}
                      </a>
                    ) : null}
                  </div>
                </Field>
              ) : null}
              <Button
                type="submit"
                disabled={busy || sendingCode || !captchaReady}
              >
                {busy ? t("working") : t("submit")}
              </Button>
            </FieldGroup>
          </form>
        ) : config ? (
          <p role="status">{t("disabled")}</p>
        ) : null}
        <div className="mt-4 min-h-12" aria-live="polite" aria-atomic="true">
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </div>
        {!config && error ? (
          <Button
            variant="outline"
            className="mt-3"
            onClick={() => setReload((value) => value + 1)}
          >
            {t("retry")}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          className="mt-4 w-full"
          disabled={busy}
          onClick={() => onBack()}
        >
          {t("back")}
        </Button>
      </div>
    </AuthShell>
  )
}
