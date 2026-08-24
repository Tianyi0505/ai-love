import { Link } from "react-router-dom";

import { qqAvatarUrl, type PersonSummary } from "../core/api";

export function ContactCard({ person }: { person: PersonSummary }) {
  return (
    <Link className="contact-card" to={`/memory/people/${person.person_id}`}>
      <img src={qqAvatarUrl(person.qq)} alt={`${person.display_name} 的 QQ 头像`} />
      <strong>{person.display_name}</strong>
    </Link>
  );
}
