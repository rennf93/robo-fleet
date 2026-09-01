import { redirect } from "next/navigation";

export default function ProductsPage() {
  redirect("/workstation?tab=products");
}
