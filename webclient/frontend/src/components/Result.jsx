import React, { useEffect, useState } from "react";
import Answer from "./Answer.jsx";
import { LuAnnoyed } from "react-icons/lu";
import RelatedQuestion from "./RelatedQuestion";
import Sources from "./Sources";
import {parseStreaming} from "../util/parseStream.js"

const Result = ({ query, rid }) => {
  const [sources, setSources] = useState([]);
  const [markdown, setMarkdown] = useState("");
  const [relates, setRelates] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    void parseStreaming(
      controller,
      query,
      rid,
      setSources,
      setMarkdown,
      setRelates,
      setError
    );
    return () => controller.abort();
  },[query]);

  console.log();
  return (
    <div className="flex flex-col gap-8">
      <Answer markdown={markdown} sources={sources}></Answer>
      <Sources sources={sources}></Sources>
      <RelatedQuestion relates={relates}></RelatedQuestion>
      {error && (
        <div className="absolute inset-4 flex items-center justify-center bg-white/40 backdrop-blur-sm">
          <div className="p-4 bg-white shadow-2xl rounded text-blue-500 font-medium flex gap-4">
            <LuAnnoyed/>
            {error === 429
              ? "Sorry, you have made too many requests recently, try again later."
              : "Sorry, we might be overloaded, try again later."}
          </div>
        </div>
      )}
    </div>
  );
};

export default Result;
