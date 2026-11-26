import { redirect } from "next/navigation"

/** Dedicated administrator sign-in entry; the public login page has no local-login switch. */
export default function AdminLoginEntry() {
  redirect("/#/admin-login")
}
