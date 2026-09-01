import { redirect } from "next/navigation";

export default function A2APage() {
  redirect("/agents?tab=conversations");
}
