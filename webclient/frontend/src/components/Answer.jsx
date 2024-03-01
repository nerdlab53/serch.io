import React from "react";
import Wrapper from "./Wrapper";
import Skeleton from "./Skeleton";
import { FaBookReader } from "react-icons/fa";
import Markdown from "react-markdown";

const Answer = ({ markdown, sources }) => {
  return (
    <Wrapper
      title={
        <>
          <FaBookReader /> Answer
        </>
      }
      content={
        markdown ? (
          <div className="prose prose-sm max-w-full">
            <Markdown
              components={{
                a: ({ node_, ...props }) => {
                  if (!props.href) return <></>;
                  const source = sources[+props.href - 1];
                  if (!source) return <></>;
                  return (
                    <span className="inline-block w-4">
                          <span
                            title={source.name}
                            className="inline-block cursor-pointer transform scale-[60%] no-underline font-medium bg-zinc-300 hover:bg-zinc-400 w-6 text-center h-6 rounded-full origin-top-left"
                          >
                            {props.href}
                          </span>
                        <div
                          className="max-w-screen-md flex flex-col gap-2 bg-white shadow-transparent ring-zinc-50 ring-4 text-xs"
                        >
                          <div className="text-ellipsis overflow-hidden whitespace-nowrap font-medium">
                            {source.name}
                          </div>
                          <div className="flex gap-4">
                            {source.primaryImageOfPage?.thumbnailUrl && (
                              <div className="flex-none">
                                <img
                                  className="rounded h-16 w-16"
                                  width={source.primaryImageOfPage?.width}
                                  height={source.primaryImageOfPage?.height}
                                  src={source.primaryImageOfPage?.thumbnailUrl}
                                />
                              </div>
                            )}
                            <div className="flex-1">
                              <div className="line-clamp-4 text-zinc-500 break-words">
                                {source.snippet}
                              </div>
                            </div>
                          </div>

                          <div className="flex gap-2 items-center">
                            <div className="flex-1 overflow-hidden">
                              <div className="text-ellipsis text-blue-500 overflow-hidden whitespace-nowrap">
                                <a
                                  title={source.name}
                                  href={source.url}
                                  target="_blank"
                                >
                                  {source.url}
                                </a>
                              </div>
                            </div>
                            <div className="flex-none flex items-center relative">
                              <img
                                className="h-3 w-3"
                                alt={source.url}
                                src={`https://www.google.com/s2/favicons?domain=${source.url}&sz=${16}`}
                              />
                            </div>
                          </div>
                        </div>
                    </span>
                  )
                },
              }}
            >
              {markdown}
            </Markdown>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Skeleton className="max-w-sm h-4 bg-zinc-200"></Skeleton>
            <Skeleton className="max-w-lg h-4 bg-zinc-200"></Skeleton>
            <Skeleton className="max-w-2xl h-4 bg-zinc-200"></Skeleton>
            <Skeleton className="max-w-lg h-4 bg-zinc-200"></Skeleton>
            <Skeleton className="max-w-xl h-4 bg-zinc-200"></Skeleton>
          </div>
        )
      }
    ></Wrapper>
  );
};

export default Answer;
