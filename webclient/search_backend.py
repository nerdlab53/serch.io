import concurrent.futures
import glob
import json
import os
import re
import threading
import requests
import traceback
from typing import Annotated, List, Generator, Optional

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
import httpx
from loguru import logger

import leptonai
from leptonai import Client
from leptonai.kv import KV
from leptonai.photon import Photon, StaticFiles
from leptonai.photon.types import to_bool
from leptonai.api.workspace import WorkspaceInfoLocalRecord
from leptonai.util import tool

# only using serper/searchapi for this
SERPER_SEARCH_ENDPOINT = "https://google.serper.dev/search"
SEARCHAPI_SEARCH_ENDPOINT = "https://www.searchapi.io/api/v1/search"


# reference count
REFERENCES_COUNT = 4

# return error after exceeding the limit below
DEFAULT_SEARCH_ENGINE_TIMEOUT = 5


# def query
def_query = "Which character on the show 'The Big Bang Theory' idolizes Spock the most?"

# rag query
_rag_query_text = """
You are a large language AI assistant. You are given a user question, and please write clean, concise and accurate answer to the question. You will be given a set of related contexts to the question, each starting with a reference number like [[citation:x]], where x is a number. Please use the context and cite the context at the end of each sentence if applicable.

Your answer must be correct, accurate and written by an expert using an unbiased and professional tone. Please limit to 1024 tokens. Do not give any information that is not related to the question, and do not repeat. Say "information is missing on" followed by the related topic, if the given context do not provide sufficient information.

Please cite the contexts with the reference numbers, in the format [citation:x]. If a sentence comes from multiple contexts, please list all applicable citations, like [citation:3][citation:5]. Other than code and specific names and citations, your answer must be written in the same language as the question.

Here are the set of contexts:

{context}

Remember, don't blindly repeat the contexts verbatim. And here is the user question:
"""

# stop words for removal
stop_words = [
    "<|im_end|>",
    "[End]",
    "[end]",
    "\nReferences:\n",
    "\nSources:\n",
    "End.",
]

_more_questions_prompt = """
You are a helpful assistant that helps the user to ask related questions, based on user's original question and the related contexts. Please identify worthwhile topics that can be follow-ups, and write questions no longer than 20 words each. Please make sure that specifics, like events, names, locations, are included in follow up questions so they can be asked standalone. For example, if the original question asks about "the Manhattan project", in the follow up question, do not just say "the project", but use the full name "the Manhattan project". Your related questions must be in the same language as the original question.

Here are the contexts of the question:

{context}

Remember, based on the original question and related contexts, suggest three such further questions. Do NOT repeat the original question. Each related question should be no longer than 20 words. Here is the original question:
"""


def search_with_serper(query: str, key: str):
    """
    Search with Serper API and return the contexts
    """
    payload = json.dumps(
        {
            "q": query,
            "num": (
                REFERENCES_COUNT 
                if REFERENCES_COUNT % 10 == 0 
                else (REFERENCES_COUNT // 10 + 1) * 10
            ),
        }
    )

    headers = {"X-API-KEY": key, "ContentType": "application/json"}
    logger.info(
        f'{payload} {headers} {key} {query} {SERPER_SEARCH_ENDPOINT}'
    )
    response = requests.post(
        SERPER_SEARCH_ENDPOINT,
        headers=headers,
        data=payload,
        timeout=DEFAULT_SEARCH_ENGINE_TIMEOUT
    )
    if not response.ok:
        logger.error(f"{response.status_code} {response.text}")
        raise HTTPException(response.status_code, "search engine error.")
    content = response.json()
    try:
        contexts = []
        if content.get('knowledgeGraph'):
            url = content['knowledgeGraph'].get(
                "descriptionUrl") or content['knowledgeGraph'].get('website')
            snippet = content['knowledgeGraph'].get('description')
            if url and snippet:
                contexts.append({
                    "name": content['knowledgeGraph'].get('title', ""),
                    "url": url,
                    "snippet": snippet
                })
        if content.get('answerBox'):
            url = content['answerBox'].get("url")
            snippet = content['answerBox'].get(
                'snippet') or content['answerBox'].get('answer')
            if url and snippet:
                contexts.append({
                    "name": content['answerBox'].get('title', ""),
                    "url": url,
                    "snippet": snippet
                })

        contexts += [
            {"name": c["title"], "url": c["link"],
                "snippet": c.get["snippet", ""]}
            for c in content["organic"]
        ]
        return contexts[:REFERENCES_COUNT]
    except KeyError:
        logger.error(f'Error encountered : {content}')
    return []


def search_with_searchapi(query: str, key: str):
    """
    Search with SearchAPI.io and return the contexts
    """
    payload = {
        "q": query,
        "engine": "google",
        "num": (
            REFERENCES_COUNT
            if REFERENCES_COUNT % 10 == 0
            else (REFERENCES_COUNT // 10 + 1) * 10
        ),
    }
    headers = {"Authorization": f"Bearer {key}",
               "Content-Type": "application/json"}
    logger.info(
        f"{payload} {headers} {key} {query} {SEARCHAPI_SEARCH_ENDPOINT}"
    )
    response = requests.get(
        SEARCHAPI_SEARCH_ENDPOINT,
        headers=headers,
        params=payload,
        timeout=30
    )
    if not response.ok:
        logger.error(f"{response.status_code} {response.text}")
        raise HTTPException(response.status_code, "Search engine error.")
    json_content = response.json()
    try:
        # get contexts
        contexts = []
        if json_content.get("answer_box"):
            if json_content["answer_box"].get("organic_result"):
                title = json_content["answer_box"].get("organic_result").get("title", "")
                url = json_content["answer_box"].get("organic_result").get("link", "")
            if json_content["answer_box"].get("type") == "population_graph":
                title = json_content["answer_box"].get("place", "")
                url = json_content["answer_box"].get("explore_more_link", "")

            title = json_content["answer_box"].get("title", "")
            url = json_content["answer_box"].get("link")
            snippet = json_content["answer_box"].get("answer") or json_content["answer_box"].get("snippet")

            if url and snippet:
                contexts.append({
                    "name": title,
                    "url": url,
                    "snippet": snippet
                })

        if json_content.get("knowledge_graph"):
            if json_content["knowledge_graph"].get("source"):
                url = json_content["knowledge_graph"].get("source").get("link", "")

            url = json_content["knowledge_graph"].get("website", "")
            snippet = json_content["knowledge_graph"].get("description")

            if url and snippet:
                contexts.append({
                    "name": json_content["knowledge_graph"].get("title", ""),
                    "url": url,
                    "snippet": snippet
                })

        contexts += [
            {"name": c["title"], "url": c["link"],"snippet": c.get("snippet", "")} for c in json_content["organic_results"]
        ]

        if json_content.get("related_questions"):
            for question in json_content["related_questions"]:
                if question.get("source"):
                    url = question.get("source").get("link", "")
                else:
                    url = ""
                snippet = question.get("answer", "")

                if url and snippet:
                    contexts.append({
                        "name": question.get("question", ""),
                        "url": url,
                        "snippet": snippet
                    })

            return contexts[:REFERENCES_COUNT]
    except KeyError:
        logger.info(f"Error encountered : {json_content}")
        return []


class RAG(Photon):
    requirement_dependency = [
        "openai",  # for openai client usage.
    ]
    extra_files = glob.glob("ui/**/*", recursive=True)
    deployment_template = {
        "resource_shape": "cpu.small",
        "env": {
            # using lepton as backend
            "BACKEND": "LEPTON",
            # specify the search cx if using google
            "GOOGLE_SEARCH_CX": "",
            # specify the LLM used
            "LLM_MODEL": "mixtral-8x7B",
            "KV_NAME": "search-with-lepton",
            "RELATED_QUESTIONS": "true",
            "LEPTON_ENABLE_AUTH_BY_COOKIE": "true",
        },
        # secrets such as api keys etc.
        "secret": [
            "SERPER_SEARCH_API_KEY",
            "SEARCHAPI_API_KEY",
            "LEPTON_WORKSPACE_TOKEN",
        ],
    }

    '''
        As we'll only be making a bunch of API calls we can keep this to a good amount
        '''
    max_concurrency = 16

    def local_client(self):
        '''
        If using OpenAI API
        '''
        import openai
        thread_local = threading.local()
        try:
            return thread_local.client
        except AttributeError:
            thread_local.client = openai.OpenAI(
                base_url=f"https://{self.model}.lepton.run/api/v1/",
                api_key=os.environ.get("LEPTON_WORKSPACE_TOKEN")
                or WorkspaceInfoLocalRecord.get_current_workspace_token(),
                timeout=httpx.Timeout(
                    connect=10, read=120, write=120, pool=10),
            )
            return thread_local.client

    def init(self):
        '''
        Initialize Photon Configs
        '''
        leptonai.api.workspace.login()
        self.backend = os.environ["BACKEND"].upper()
        if self.backend == "LEPTON":
            self.leptonsearch_client = Client(
                "https://search-api.lepton.run/",
                token=os.environ.get("LEPTON_WORKSPACE_TOKEN")
                or WorkspaceInfoLocalRecord.get_current_workspace_token(),
                stream=True,
                timeout=httpx.Timeout(
                    connect=10, read=120, write=120, pool=10),
            )
        elif self.backend == "SERPER":
            self.search_api_key = os.environ["SERPER_API_KEY"]
            self.search_function = lambda query: search_with_serper(
                query,
                self.search_api_key
            )
        elif self.backend == "SEARCHAPI":
            self.search_api_key = os.environ["SEARCHAPI_API_KEY"]
            self.search_function = lambda query: search_with_searchapi(
                query,
                self.search_api_key
            )
        else:
            raise RuntimeError(
                "Backend must be LEPTON, SERPER or SEARCHAPI.")
        self.model = os.environ["LLM_MODEL"]
        self.executor = concurrent.futures.ThreadPoolExecutor(
            # An exector to carry out async tasks, such as uploading to KV.
            max_workers=self.handler_max_concurrency * 2
        )
        # Create the KV to store the search results.
        logger.info("Creating KV. May take a while for the first time.")
        self.kv = KV(
            os.environ["KV_NAME"], create_if_not_exists=True, error_if_exists=False
        )
        self.should_do_related_questions = to_bool(
            os.environ['RELATED_QUESTIONS'])

    def get_related_questions(self, query, contexts):
        '''
        Gets related questions based on the query and contexts
        '''
        def ask_related_questions(
            questions: Annotated[
                List[str],
                [(
                    "question",
                    Annotated[
                        str, "related question to the original question and context."
                    ],
                )],
            ]
        ):
            '''
            ask further questions that are related to the input and output.
            '''
            pass

        try:
            response = self.local_client().chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": _more_questions_prompt.format(
                            context="\n\n".join([c["snippet"] for c in contexts])
                        ),
                    },
                    {
                        "role": "user",
                        "content": query,
                    },
                ],
                tools=[{
                    "type": "function",
                    "function": tool.get_tools_spec(ask_related_questions),
                }],
                max_tokens=512,
            )
            related = response.choices[0].message.tool_calls[0].function.arguments
            if isinstance(related, str):
                related = json.loads(related)
            logger.trace(f"Related questions {related}")
            return related['questions'][:5]
        except Exception as e:
            logger.error(
                "encountered an error while generating related responses:"
                f" {e}\n {traceback.format_exc()}"
            )
            return []

    def _raw_stream_response(
        self, contexts, llm_response, related_questions_future
    ) -> Generator[str, None, None]:
        """
        A function which yields the raw stream response
        """
        yield json.dumps(contexts)
        yield "\n___LLM_RESPONSE___\n"
        if not contexts:
            yield (
                f"Could not get the context as the search engine did not return any answer for this query."
            )
        for chunk in llm_response:
            if chunk.choices:
                yield chunk.choices[0].delta.content or ""
        if related_questions_future is not None:
            related_questions = related_questions_future.result()
            try:
                result = json.dumps(related_questions)
            except Exception as e:
                logger.error(
                    f"'Encountered error' {e}\n {traceback.format_exc()}"
                )
                result = "[]"
            yield "\n\n__RELATED_QUESTIONS__\n\n"
            yield result

    def stream_and_upload_to_kv(
        self, contexts, llm_response, related_questions_future, search_uuid
    ) -> Generator[str, None, None]:
        """
        Streams the result and uploads to KV
        """
        all_yielded_responses = []
        for result in self._raw_stream_response(
            contexts, llm_response, related_questions_future
        ):
            all_yielded_responses.append(result)
            yield result
        _ = self.executor.submit(
            self.kv.put, search_uuid,"".join(all_yielded_responses))

    @Photon.handler(method="POST", path="/query")
    def query_function(
        self,
        query: str,
        search_uuid: str,
        generate_related_questions: Optional[bool] = True
    ) -> StreamingResponse:
        """
        Query the search engine and return the response

        The query has the following fields:
            - query : the user query
            -search_uuid : a uuid used to store and retrieve each result. If
                    the uuid does not exist, generate and write to the kv. If the kv
                    fails, we generate regardless, in favor of availability. If the uuid
                    exists, return the stored result.
            -generate_related_questions : if set to false, it will not generate related questions.
                    Otherwise, will depend upon the environment variable RELATED_QUESTIONS. Default : true.
        """
        if search_uuid:
            try:
                result = self.kv.get(search_uuid)

                def str_to_generator(result: str) -> Generator[str, None, None]: 
                    yield result

                return StreamingResponse(str_to_generator(result))

            except KeyError:
                logger.info(
                    f"Key {search_uuid} not found."
                )
            except Exception as e:
                logger.info(
                    f"Error response :{e}\n {traceback.format_exc()}. Will try generating again."
                )
        else:
            raise HTTPException(
                status_code=400, detail="search_uuid must be provided.")

        if self.backend == "LEPTON":
            # delegating the work to the lepton search api
            result = self.leptonsearch_client.response(
                query=query,
                search_uuid=search_uuid,
                generate_related_questions=generate_related_questions
            )
            return StreamingResponse(content=result, media_type="text\html")

        query = query or def_query
        query = re.sub(r"\[/?INST\]", "", query)
        contexts = self.search_function(query)

        system_prompt = _rag_query_text.format(
            context="\n\n".join(
                [f"[[citation:{i+1}]] {c['snippet']}" for i, c in enumerate(contexts)]
            )
        )
        try:
            client = self.local_client()
            llm_response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                max_tokens=1024,
                stop=stop_words,
                stream=True,
                temperature=0.9
            )
            if self.should_do_related_questions and generate_related_questions:
                # generating related questions as the answer is being generated
                related_questions_future = self.executor.submit(
                    self.get_related_questions, query, contexts
                )
            else:
                related_questions_future = None
        except Exception as e:
            logger.error(
                f"encountered error : {e}\n{traceback.format_exc()}"
            )
            return HTMLResponse("Internal Server Error.", 503)
        return StreamingResponse(
            self.stream_and_upload_to_kv(
                contexts, llm_response, related_questions_future, search_uuid
            ),
            media_type="text/html"
        )

    @Photon.handler(mount=True)
    def ui(self):
        """
            ui : it is the directory containing the index.html and other components
        """
        return StaticFiles(
            directory="frontend"
        )

    @Photon.handler(method="GET", path="/")
    def index(self) -> RedirectResponse:
        """
            Redirects the "/" to the ui page
        """
        return RedirectResponse(url="frontend/index.html")


if __name__ == "__main__":
    rag = RAG()
    rag.launch()

