# Vibe Coding a DDS Implementation: Semi-Automated Development of Complex Systems Software

*How an AI agent built a working DDS middleware in Python and Rust — and achieved basic interoperability with RTI Connext DDS across 3 active days of work.*

## How it started

This story begins at RTI's Company Kickoff (CKO) in the last week of January 2026. The research team was together, and conversations kept coming back to the same question: how do we show people how powerful automated software development has become? We'd all seen the demos. Cursor had just shipped a three-million-line browser that "kinda worked." The capabilities were advancing faster than anyone's intuition about what was possible, and even technical audiences were skeptical.

Someone floated a thought experiment: what if you tried to vibe code a DDS implementation?

We chose DDS deliberately. Everyone at RTI — not just the development team — understands the complexity of DDS and the difficulty of getting an implementation right. Sales engineers have debugged interop issues. Product managers have watched multi-month integration efforts. Field engineers know what it means when `rtiddsspy` shows zero matched subscriptions. If an AI agent could build a working DDS implementation, it would land differently than a compiler or a web framework. Everyone here knows exactly how hard this is supposed to be.

The RTPS wire protocol specification alone runs to 282 pages. Connext represents decades of engineering. Getting a from-scratch implementation to interoperate with Connext is not a matter of passing a test suite you wrote yourself — Connext is the ground truth, and it will reject your packets for reasons buried in spec sections you haven't read yet.

The thought experiment turned into an actual experiment. At RTI headquarters, with a laptop left running overnight between CKO sessions, VibeDDS was born.

Could an AI agent, guided by a human acting not as a DDS expert but as a regular programmer — pointing at docs, insisting on tests, suggesting debugging techniques — build a working DDS implementation and achieve interoperability with Connext?

The answer is yes. VibeDDS is a 25,595-line project across 108 files — 4,400 lines of Python library, 7,600 lines of Rust library, and the rest in tests, interop diagnostics, examples, and tooling. The Rust implementation compiles to a 1 MB static binary. It doesn't cover the full DDS spec or the full scope of Connext — but what it does implement works, and it achieves bidirectional interoperability with RTI Connext DDS 7.3.0 across all six directed paths: Python to RTI, RTI to Python, Rust to RTI, RTI to Rust, Rust to Python, and Python to Rust.

The total active development time was approximately 11.5 hours across 3 working days, with 4-5 hours of human involvement. The other 7 days on the calendar? Nothing happened — zero commits, zero work. The agent wrote every line of code. The human never touched the keyboard for anything but prompts.

## The approach: research, plan, prototype, port

Before writing a single line of code, the foundation was laid:

**Research phase.** Nine OMG specification PDFs (DDS 1.4, DDSI-RTPS 2.5, DDS-XTypes 1.3, and six others) were converted to markdown and fed into the agent's context. This created approximately 76,000 lines of searchable specification text that the agent could reference during implementation. The agent wasn't working from blog posts or tutorials — it had the actual standards.

**Architecture decision.** One key insight shaped the entire project: *prototype in Python first, then port to Rust.* AI models generate Python more fluently than Rust, and debugging protocol issues is dramatically faster without a compile step. The plan was to get Python working through interop testing with Connext, then mechanically port the validated logic to Rust. This turned out to be the single most important decision of the project.

**CLAUDE.md as the constitution.** A `CLAUDE.md` file established the agent's operating instructions: test early and often, write unit tests for every module, write end-to-end tests for every integration point, and build incrementally through defined stages (CDR serialization, then RTPS messages, then SPDP discovery, then SEDP endpoint discovery, then pub/sub data exchange). This file persisted across sessions and acted as the agent's memory of project conventions. This mattered because the agent's natural tendency is to sprint toward the goal and declare victory — the `CLAUDE.md` was the guardrail that forced discipline.

## Days 1-2: from zero to discovery (Tuesday-Wednesday, January 27-28)

On Tuesday, the research team was in working sessions at HQ from 10 AM to 6 PM. Between sessions, the project was set up: nine OMG spec PDFs converted to markdown, the initial architecture sketched out, and the agent pointed at the task. That evening was the Engineering Department Dinner at Bay Padel in Sunnyvale. The laptop was left running.

Wednesday's CKO schedule had the research team on an excursion in San Francisco for the entire day. The laptop stayed behind at headquarters in Sunnyvale, the agent working unsupervised. By 4:50 PM, the first commit had landed: 62 files, nearly 99,000 lines (including the converted spec markdowns). The actual library code was about 3,400 lines of Python and 2,000 lines of Rust, covering CDR serialization, RTPS message building/parsing, SPDP discovery, and the beginnings of SEDP.

By the time we got back from San Francisco for Karaoke Night, the agent had built the foundation. Karaoke started at 7 PM. At 7:55 PM, while somewhere in the building people were singing, the next commit landed: Stage 6e, 7,600 additional lines covering data pub/sub, the Rust participant implementation, hello_pub/hello_sub examples, RTI interop test infrastructure, and wire compatibility tests. The agent had gone from zero to a DDS implementation with working self-discovery and data exchange while we were across the bay.

```
Jan 28 16:50  Initial commit: Python + Rust libraries, specs     98,767 lines
Jan 28 19:00  README                                                 139 lines
Jan 28 19:55  Stage 6e: Data pub/sub + RTI interop improvements    7,625 lines
```

We left it running and went to bed. By the end of the first day, VibeDDS could discover itself, exchange endpoint metadata, and publish/subscribe data between its own instances. The next challenge was making Connext accept it as a peer.

## Day 2: the interop wall (Thursday, January 29)

Thursday was packed: Genesis engagement at 8 AM, guest speakers from i3 and Wabtec, the company photo at 12:45, an AI/Research Alignment session at 2:30, and the Celebration Dinner from 7 to 11 PM.

Between all of that, the agent was working the interop problem.

RTI's `rtiddsspy` tool could see VibeDDS's published data. VibeDDS to RTI worked. But the reverse direction — RTI publishing data that VibeDDS could receive — was completely broken. RTI reported **zero matched subscriptions**. It could see VibeDDS's reader in SEDP discovery but refused to send data to it.

The 8:59 AM commit — squeezed in before the morning sessions — shows the first systematic attempt: enhanced SEDP with comprehensive QoS PIDs. By 3:28 PM, between the afternoon guest speakers, a second commit landed with 4,300 lines of interop tooling and documentation.

```
Jan 29 08:59  Enhance SEDP for RTI interop - QoS PIDs              1,451 lines
Jan 29 15:28  Document interop progress and add tooling             4,313 lines
```

The agent tried six different SEDP configurations, varying which QoS parameters were included, how XTypes metadata was formatted, and which type information blobs were sent. It captured pcap traces of RTI-to-RTI traffic and compared them byte-by-byte with VibeDDS-to-RTI traffic. It built diagnostic tools — an SEDP sniffer, a metatraffic analyzer, a matching diagnostic — that could interrogate Connext's internal state.

All six configurations failed identically. RTI still showed 0 matched subscriptions.

We left it running through the Celebration Dinner. It was still stuck when we went back to the hotel. This is where we got stuck.

## The gap: January 29 to February 5

Friday was the flight home. After that, the git log tells the real story: zero commits for an entire week. The project was stuck, and rather than throw more hours at it, it simply sat idle. Both Claude (Opus 4.5) and GPT-5.2 (via Codex) had been pointed at the problem during CKO. The agent sessions explored increasingly exotic hypotheses:

- Maybe RTI required specific vendor PIDs (proprietary parameter IDs that RTI includes in its own traffic)?
- Maybe the TypeObject blob needed to be zlib-compressed in a specific way?
- Maybe the TypeConsistency encoding needed to use RTI's compact 8-byte format instead of the full XTypes struct?

None of these were the problem. The agents were searching in the wrong layer entirely. They were debugging the *content* of SEDP messages when the actual bug was that SEDP messages weren't *arriving*.

The interop-experiments log from January 29 captures the state of the investigation:

> *"SEDP discovery occurs, but RTI still does not match the VibeDDS reader for user data flow. Likely missing requirement is TypeInformation/TypeObject or an RTI-specific vendor PID needed for matching."*

This was completely wrong. The content was fine. The transport was broken.

## February 6: Opus 4.6 breaks through

On February 5, Anthropic released Claude Opus 4.6 — and, coincidentally, published [a case study about building a C compiler](https://www.anthropic.com/engineering/building-c-compiler) using "parallel Claudes." That post was the nudge to revisit VibeDDS. A more capable model had just dropped. The next morning, February 6, a fresh session was started on the RTI interop problem.

Within **1 hour and 40 minutes**, the problem was solved.

Opus 4.6 did something the previous models hadn't: it questioned the premise. Instead of adding more PIDs to SEDP payloads, it checked whether the packets were arriving at all. It wrote a raw UDP sniffer, pointed it at VibeDDS's metatraffic port, and observed: **zero packets received from RTI**.

The fix was one line:

```python
# transport.py (BEFORE)
sock.bind((self.local_ip, self._metatraffic_unicast_port))
# Binds to e.g., 192.168.1.12:7416

# transport.py (AFTER)
sock.bind(("", self._metatraffic_unicast_port))
# Binds to INADDR_ANY — accepts packets on any interface
```

On macOS, when two DDS participants run on the same host, they communicate via `127.0.0.1`. VibeDDS's socket was bound to the machine's external IP (`192.168.1.12`), so packets sent to `127.0.0.1` on the same port were silently dropped by the kernel. The socket was literally deaf to same-host traffic.

This was root cause #1. Once packets started arriving, three more bugs fell in rapid succession:

**Root cause #2: Entity kind constants were swapped.** The RTPS spec defines `READER_NO_KEY = 0x04` and `READER_WITH_KEY = 0x07`. VibeDDS had them backwards. RTI saw what it thought was a keyed reader and refused to match it with a non-keyed writer.

**Root cause #3: Reliability wire values used API encoding instead of wire encoding.** The DDS API uses 0 for BEST_EFFORT and 1 for RELIABLE. The RTPS wire protocol uses 1 and 2. VibeDDS was sending the wrong numbers.

**Root cause #4: No loopback filtering.** VibeDDS's reader was receiving its own writer's multicast packets and processing them as remote data.

The commit at 9:55 AM tells the story:

```
Feb 06 09:55  Fix bidirectional RTI Connext DDS interop            8,039 lines
              + loopback filtering
```

8,039 lines for four one-line fixes. The rest was diagnostic tooling, test infrastructure, and documentation that the agent generated during the debugging process. This ratio — massive diagnostic scaffolding around tiny fixes — is characteristic of real protocol debugging.

## The same afternoon: Rust port and full cross-compatibility

With Python interop solved, the Rust port took 48 minutes:

```
Feb 06 10:43  Port Rust interop fixes, add 6-way cross-             927 lines
              compatibility tests
```

The agent ported the reliability wire value fix to Rust, discovered an *additional* Rust-only bug (the user unicast port formula used the wrong offset constant: D2=1 instead of D3=11, causing port collisions with RTI), fixed it, wrote interop test scripts for all six directed paths, and verified everything passed.

This is where the "prototype in Python, port to Rust" strategy paid off. Two of the four Python bugs didn't even exist in Rust — the Rust transport had always bound to `INADDR_ANY`, and loopback filtering was already implemented — because the Rust code was written *after* learning from the Python debugging. The Rust port wasn't a second debugging session. It was mechanical translation of already-validated logic, plus one new bug that only manifested during cross-implementation testing.

## The numbers

**Timeline (3 active days out of 10 calendar days):**

| Date | Active Time | What Happened |
|------|-----------|---------------|
| Jan 28 (Day 1) | ~3 hours | Zero to working DDS with self-interop |
| Jan 29 (Day 2) | ~6 hours | RTI interop attempt: one direction works, reverse blocked |
| Jan 30 - Feb 5 | 0 hours | No commits. Nobody worked on it. |
| Feb 6 (Day 3) | ~2.5 hours | Full interop: Python↔RTI (1h40m) + Rust port (48m) |

Total active development time: **~11.5 hours.** The 7-day gap between January 29 and February 6 was not debugging time — it was simply idle. The project sat untouched until a more capable model became available.

**Code produced (25,595 lines across 108 files):**

| | Lines | Files |
|---|------:|------:|
| **Python Implementation** | **10,846** | |
| Library (vibedds/) | 4,398 | 15 |
| Tests | 5,477 | 12 |
| Examples | 971 | 10 |
| **Rust Implementation** | **8,620** | |
| Library (src/) | 7,578 | 14 |
| Tests | 485 | 1 |
| Examples | 557 | 6 |
| **Other** | **6,129** | |
| Scripts & tools | 1,227 | 7 |
| RTI interop test suite | 3,704 | 22 |
| Documentation | 1,187 | 6 |
| Config | 11 | 1 |

**Compiled binary:** The Rust library builds to a **1,016 KB** release binary — a complete DDS implementation with SPDP, SEDP, pub/sub, and RTI interoperability in under a megabyte.

**Human involvement:** 4-5 hours of active guidance out of ~11.5 hours of total development time. The human wrote zero lines of code. Not a single line. But the human's role was critical — it just wasn't coding:

- **Testing discipline.** The agent consistently wanted to skip tests and declare victory. Left to its own devices, it would sprint to "working" code that had bugs it hadn't checked for. The human's most important recurring intervention was insisting on test-early-test-often: unit tests for every module, end-to-end tests at every integration point, and interop tests before declaring anything done.
- **Debugging direction.** The human suggested using UDP sniffers to examine raw packets. The human explained how DDS discovery actually works — the SPDP/SEDP handshake sequence, what metatraffic ports are for, why a socket bound to the wrong address would be deaf. This domain knowledge guided the agent toward productive debugging rather than flailing.
- **Architecture decisions.** Python first, Rust second. Test against RTI, not just against yourself. Use distinct participant IDs to avoid port collisions. These weren't coding decisions — they were strategy.
- **Spec adherence.** The agent would sometimes drift from the specification, implementing what seemed reasonable rather than what the RTPS spec actually said. The human's role was to push back: read the spec, pay attention to the spec, the spec is the ground truth.

The pattern is clear: the human contributed zero code but 100% of the engineering judgment. The agent was the hands; the human was the experience.

**Specifications consumed:** 9 OMG spec PDFs (19 MB total), converted to 76,000 lines of markdown, referenced continuously by the agent during implementation.

## What the agent was good at

**Specification interpretation.** The agent could read RTPS Section 9.3.1.2 (entity kind definitions) and Section 9.4.2.13 (reliability wire encoding) and translate them into code correctly — when pointed at the right section. The bugs it introduced weren't from misreading the spec; they were from not reading the *right part* of the spec in the first place.

**Diagnostic tooling.** When debugging interop, the agent spontaneously created UDP sniffers, SEDP payload decoders, pcap analyzers, and RTI perspective diagnostics. The ratio of diagnostic code to fix code was roughly 100:1. This mirrors how experienced systems programmers work — you spend most of your time building tools to see the problem, and the fix itself is trivial.

**Mechanical porting.** Once the Python implementation was validated, porting to Rust was fast and accurate. The agent understood the mapping between Python patterns and Rust idioms and didn't introduce new logic bugs during translation (it did introduce one port constant bug, caught by interop testing).

**Test generation.** The agent produced comprehensive test suites without being asked. The final project has 171 unit tests, 17 wire compatibility tests, and 6 end-to-end interop tests covering every directed pair of {Python, Rust, RTI}.

## What the agent was bad at

**Layer jumping.** The critical week-long block happened because the agent kept debugging SEDP *content* when the problem was in the *transport*. It tried six different SEDP configurations, built elaborate packet comparison tools, and generated pages of analysis about TypeObject encoding differences — all completely irrelevant because the packets weren't arriving in the first place. A human network engineer would have run `tcpdump` in the first five minutes.

**Questioning premises.** The agent accepted "SEDP content must be wrong" as the frame and never stepped back to ask "are the packets arriving?" This is the AI equivalent of searching for your keys under the streetlight because that's where the light is. Opus 4.6 broke through specifically because it questioned the premise that earlier models had accepted.

**Recognizing macOS quirks.** The `INADDR_ANY` binding issue and `SO_REUSEPORT` packet stealing are macOS-specific behaviors that aren't in any DDS specification. They're tribal knowledge. The agent had no way to know about them except through systematic experimentation, and it took a more capable model to perform that experimentation effectively.

## The scaffolding process

The workflow that produced VibeDDS isn't a single-shot code generation. It's a scaffolded process:

1. **Research.** Feed the agent specifications, documentation, and reference implementations. For VibeDDS, this was 9 OMG specifications converted to searchable markdown.

2. **Plan.** Discuss the approach with the agent. Establish the key architectural decisions (Python first, Rust second). Create a phased implementation plan.

3. **CLAUDE.md.** Write the constitution: test early, test often, test at every layer. This file persists across sessions and keeps the agent on track.

4. **Implement.** The agent sprints. It will produce working code fast but make subtle mistakes — swapped constants, wrong wire encodings, binding to the wrong address. The code works against itself but fails against real-world implementations.

5. **Interop testing.** This is where the real debugging happens. Unit tests verify self-consistency; interop tests verify correctness. The D2/D3 port formula bug in Rust passed all unit tests but failed immediately when sharing a network with RTI.

6. **Loop.** When the agent gets stuck, escalate model capability, change the debugging frame, or provide human insight. The breakthrough on VibeDDS came from a combination of a more capable model and the accumulated diagnostic tooling from previous sessions.

For production projects, this loop can be further automated. Attach a review agent that scans for bugs, dead code, and missing documentation, filing GitHub issues with reproduction cases. Attach a fix agent that works through those issues. Attach a review agent that validates the fixes. This "Ralph Wiggum loop" — repeatedly running an agent against its own output — is surprisingly effective at cleaning up the mess that the initial sprint inevitably creates.

## What this means for complex systems

VibeDDS is not a toy. DDS is a real protocol used in safety-critical systems. The RTPS wire protocol has specific byte-level requirements for interoperability. Getting it wrong means your autonomous vehicle can't talk to its sensor fusion pipeline. The fact that an AI agent could build a working, interoperable implementation — with human guidance measured in single-digit hours — has implications beyond DDS.

The pattern that emerged is: **AI agents are excellent at implementing known protocols from specifications, but they struggle with the environmental and integration issues that make real-world systems hard.** Socket binding semantics, OS-specific multicast behavior, the difference between wire encoding and API encoding — these are the kinds of bugs that live in the gaps between specifications, and they're where human expertise (or more capable models) makes the difference.

The trajectory is clear. The gap between "works against itself" and "works against the industry-standard implementation" is closing fast. For VibeDDS, that gap was four bugs and one model generation. The next generation of agent-built systems software will close it faster.

We should be prepared.

---

*VibeDDS is open source. The full commit history, interop test results, and debugging writeup are available at [github.com/sploithunter/VibeDDS](https://github.com/sploithunter/VibeDDS). The project was built using Claude Code with Claude Opus 4.5 and 4.6.*
