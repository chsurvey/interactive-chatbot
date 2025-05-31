import asyncio
import os
import sys
from typing import List, Dict, Optional

import websockets
from dotenv import load_dotenv
from openai import OpenAI  # openai >= 1.0.0

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key)


class ChatClient:
    """Abstract WebSocket chat client base."""

    def __init__(self, uri: str):
        self.uri = uri

    async def connect(self):
        async with websockets.connect(self.uri) as ws:
            await self.on_connect(ws)
            await self.run_tasks(ws)

    # ------------------------------------------------------------------ #
    # Lifecycle hooks – subclasses can override as needed                #
    # ------------------------------------------------------------------ #
    async def on_connect(self, ws):
        """Called once when the websocket is ready."""
        pass

    async def run_tasks(self, ws):
        """Gather send / recv / extra tasks."""
        tasks = [self.send_loop(ws), self.recv_loop(ws), *self.extra_tasks(ws)]
        await asyncio.gather(*tasks)

    async def send_loop(self, ws):
        raise NotImplementedError

    async def recv_loop(self, ws):
        async for message in ws:
            await self.on_message(message, ws)

    async def on_message(self, message: str, ws):
        print(message)

    def extra_tasks(self, ws):
        return []

    def run(self):
        try:
            asyncio.run(self.connect())
        except KeyboardInterrupt:
            print("Disconnected.")


class GUIUserClient(ChatClient):
    """User client that integrates with a GUI entry widget."""

    def __init__(self, uri: str, display_callback):
        super().__init__(uri)
        self.display_callback = display_callback
        self.send_queue: asyncio.Queue[str] = asyncio.Queue()

    def send_message(self, msg: str) -> None:
        self.send_queue.put_nowait(msg)

    async def send_loop(self, ws):
        while True:
            msg = await self.send_queue.get()
            await ws.send(msg)

    async def on_message(self, message: str, ws):
        self.display_callback(f"Friend: {message}")


# ---------------------------------------------------------------------- #
#                       GPT BACKGROUND BOT                                #
# ---------------------------------------------------------------------- #

class GPTClient(ChatClient):
    """GPT‑powered background chat bot that fulfils the 3‑step spec.

    Step‑1  – Classify the user’s intent for the *next* sentence type.
    Step‑2  – Asynchronously decide if it is our turn to speak (issue "talk").
    Step‑3  – When talk is issued, craft the actual reply and send it.
    """

    #: Allowed next‑sentence types (Korean labels kept short for simplicity)
    SENTENCE_TYPES = {
        "ack": "간결한 호응",        # short acknowledgement / back‑channel
        "op": "의견·제안",           # suggestion or opinion
        "new": "새 주제",            # start new topic
        "bye": "대화 종료"            # polite closing
    }

    def __init__(self, uri: str, model: str = "gpt-3.5-turbo"):
        super().__init__(uri)
        self.model = model
        # Full conversation history (OpenAI format)
        self.message_history: List[Dict[str, str]] = [
            {"role": "system", "content": "컴퓨터공학과 대학생 친구이다. 인터넷 커뮤니티 댓글같은 단답 위주의 20대 남성의 말투 소유."}
        ]
        # Whether we have a pending reply to send
        self.pending_sentence_type: Optional[str] = None
        # Seconds to wait before speaking if user hasn’t typed further
        self.idle_seconds_before_talk = 2.0
        # Timestamp (monotonic) of last user message we saw
        self._last_user_ts: float = 0.0

    # ------------------------ Life‑cycle hooks ------------------------ #

    async def send_loop(self, ws):
        """Bot does not spontaneously send messages here; talk_loop will."""
        await asyncio.Future()  # keep coroutine alive

    async def on_message(self, message: str, ws):
        """Called whenever a user message arrives on the socket."""
        # 1) Append to history
        self.message_history.append({"role": "user", "content": message})
        self._last_user_ts = asyncio.get_running_loop().time()
        # 2) Classify what kind of answer the user probably wants
        loop = asyncio.get_running_loop()
        sentence_type: str = await loop.run_in_executor(None, self._classify_intent, message)
        # 3) Store – talk_loop will pick this up and send when appropriate
        self.pending_sentence_type = sentence_type

    def extra_tasks(self, ws):
        return [self._talk_loop(ws)]

    # --------------------- Core asynchronous loops ------------------- #

    async def _talk_loop(self, ws):
        """Every few hundred ms decide whether to speak and, if so, reply."""
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(0.3)
            # Preconditions: is there something to say?
            if self.pending_sentence_type is None:
                continue  # nothing queued
            # Check if we already replied after the *last* user message
            if self.message_history and self.message_history[-1]["role"] == "assistant":
                # We already talked, clear the pending flag
                self.pending_sentence_type = None
                continue
            # Has the user been idle long enough?
            since_last_user = loop.time() - self._last_user_ts
            if since_last_user < self.idle_seconds_before_talk:
                continue  # give user more time to keep typing
            # ---- Issue talk: generate reply and send ----
            sentence_type = self.pending_sentence_type
            self.pending_sentence_type = None  # reset before generation
            reply = await loop.run_in_executor(None, self._generate_reply, sentence_type)
            await ws.send(reply)
            self.message_history.append({"role": "assistant", "content": reply})
            # Optional: log to stdout so log window can show it
            print(f"[GPT → user ({sentence_type})] {reply}", flush=True)

    # --------------------- OpenAI helper functions ------------------- #

    def _classify_intent(self, last_user_msg: str) -> str:
        """Return one of "ack" | "op" | "new" | "bye"."""
        system_prompt = (
            "너는 대화 분석기다. 사용자의 마지막 메시지를 보고, "
            "상대가 다음 단계에서 원하는 답변 유형을 아래 네 가지 중 하나의 "
            "key 로만 출력해라 (텍스트 말고 JSON 도 말고, key 단독).\n"
            "ack  – 간결한 호응 (맞장구, 네 등)\n"
            "op   – 의견 또는 제안\n"
            "new  – 새로운 주제 시작\n"
            "bye  – 대화 종료\n"
            "주의: 딱 한 단어(key)만 출력해야 한다."
        )
        try:
            completion = openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": last_user_msg},
                ],
                temperature=0.0,  # deterministic classification
                max_tokens=1,
            )
            key = completion.choices[0].message.content.strip().lower()
        except Exception as e:
            print(f"[classify error] {e}")
            key = "ack"
        if key not in self.SENTENCE_TYPES:
            key = "ack"
        return key

    def _generate_reply(self, sentence_type: str) -> str:
        """Generate the actual assistant sentence based on the required type."""
        type_desc = self.SENTENCE_TYPES.get(sentence_type, "간결한 호응")
        sys_msg = (
            "너는 20대 남성 대학생 친구로, 인터넷 커뮤니티 단답 같은 가벼운 말투를 사용한다. "
            "지금은 상대가 원하는 답변 유형이 '" + type_desc + "' 라는 정보를 알고 있다. "
            "그 유형에 맞는 한두 문장만 출력해라."
        )
        try:
            completion = openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_msg},
                    *self.message_history[-5:],  # recent context only
                ],
                temperature=0.7,
                max_tokens=80,
            )
            reply = completion.choices[0].message.content.strip()
        except Exception as e:
            reply = f"[GPT error] {e}"
        return reply


# ---------------------------------------------------------------------- #
#                         ENTRY‑POINT HELPER                              #
# ---------------------------------------------------------------------- #


def create_client(role: str, uri: str, gui_display_cb=None):
    if role == "gpt":
        return GPTClient(uri)
    if role == "gui_user":
        if gui_display_cb is None:
            raise ValueError("GUI display callback required for gui_user")
        return GUIUserClient(uri, gui_display_cb)
    raise ValueError("role must be 'gpt' or 'gui_user'")


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "gpt"
    client = create_client(role, "ws://localhost:8765")
    client.run()
