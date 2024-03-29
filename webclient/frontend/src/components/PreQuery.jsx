import {Link} from "react-router-dom";
import {nanoid} from "nanoid";
import { useMemo } from "react";
import { getSearchUrl } from "../util/getSearchUrl.js";

const PreQuery = ({ query }) => {
  const rid = useMemo(() => nanoid(), [query]);

  return (
    <Link
      title={query}
      to={getSearchUrl(query, rid)}
      className="border border-zinc-200/50 text-ellipsis overflow-hidden text-nowrap items-center rounded-lg bg-zinc-100 hover:bg-zinc-200/80 hover:text-zinc-950 px-2 py-1 text-xs font-medium text-zinc-600"
    >
      {query}
    </Link>
  );
};

export default PreQuery;
