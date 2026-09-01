import { redirect } from "next/navigation";

export default function JournalsPage() {
  redirect("/agents?tab=journals");
}
