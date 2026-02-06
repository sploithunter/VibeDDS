# Vibe Coding a DDS Implementation: Semi-Automated Development of Complex Systems Software

*How an AI agent built a working DDS middleware in Python and Rust — and achieved full interoperability with RTI Connext DDS across 3 active days of work.*

## How it started

This story begins at RTI's Company Kickoff (CKO) in the last week of January 2026. The research team was together, and conversations kept circling back to the same theme: automated software development is becoming shockingly capable, but it's hard to convince people — even technical people — of just how far it's come. Anthropic had recently published [a case study](https://www.anthropic.com/engineering/building-c-compiler) about building a C compiler using "parallel Claudes" — nearly 2,000 Claude Code sessions producing a 100,000-line compiler. Impressive, but compilers are a well-understood domain with clear test oracles. What about something messier? Something with wire protocols, interoperability requirements, and a real-world implementation to validate against?

Someone floated a thought experiment: what if you tried to vibe code a DDS implementation?

We chose DDS deliberately. Everyone at RTI — not just the development team — understands the complexity of the DDS protocol and the difficulty of getting an implementation right. Sales engineers have debugged interop issues. Product managers have watched multi-month integration efforts. Field engineers know what it means when `rtiddsspy` shows zero matched subscriptions. If an AI agent could build a working DDS implementation, it would resonate with this audience in a way that a compiler or a web framework wouldn't. Everyone here knows exactly how hard this is supposed to be.

DDS is a publish-subscribe middleware standard governed by the OMG, used in defense, autonomous vehicles, robotics, and industrial IoT. RTI Connext DDS — our own product — represents decades of engineering. The RTPS wire protocol specification alone runs to 282 pages. Getting a from-scratch implementation to interoperate with RTI Connext is not a matter of passing a test suite you wrote yourself — RTI's implementation is the ground truth, and it will reject your packets for reasons buried in spec sections you haven't read yet.

The thought experiment turned into an actual experiment. Between CKO sessions, on hotel Wi-Fi, VibeDDS was born.

Could an AI agent, guided by a human who understands the domain but doesn't write the code, build a working DDS implementation and achieve interoperability with RTI Connext?

The answer is yes. VibeDDS is a 25,595-line project across 108 files — 4,400 lines of Python library, 7,600 lines of Rust library, and the rest in tests, interop diagnostics, examples, and tooling. The Rust implementation compiles to a 1 MB static binary. It achieves full bidirectional interoperability with RTI Connext DDS 7.3.0 across all six directed paths: Python to RTI, RTI to Python, Rust to RTI, RTI to Rust, Rust to Python, and Python to Rust.

The total active development time was approximately 11.5 hours across 3 working days, with 4-5 hours of human involvement. The other 7 days on the calendar? Nothing happened — zero commits, zero work. The agent wrote essentially all of the code.

## The approach: research, plan, prototype, port

Before writing a single line of code, the foundation was laid:

**Research phase.** Nine OMG specification PDFs (DDS 1.4, DDSI-RTPS 2.5, DDS-XTypes 1.3, and six others) were converted to markdown and fed into the agent's context. This created approximately 76,000 lines of searchable specification text that the agent could reference during implementation. The agent wasn't working from blog posts or tutorials — it had the actual standards.

**Architecture decision.** One key human insight shaped the entire project: *prototype in Python first, then port to Rust.* AI models generate Python more fluently than Rust, and debugging protocol issues is dramatically faster without a compile step. The plan was to get Python fully correct through interop testing with RTI, then mechanically port the validated logic to Rust. This turned out to be the single most important decision of the project.

**CLAUDE.md as the constitution.** A `CLAUDE.md` file established the agent's operating instructions: test early and often, write unit tests for every module, write end-to-end tests for every integration point, and build incrementally through defined stages (CDR serialization, then RTPS messages, then SPDP discovery, then SEDP endpoint discovery, then pub/sub data exchange). This file persisted across sessions and acted as the agent's memory of project conventions.

## Day 1: from zero to discovery (January 27-28)

The initial commit landed on January 28 at 4:50 PM with 62 files and nearly 99,000 lines (including the converted spec markdowns). The actual library code was about 3,400 lines of Python and 2,000 lines of Rust — covering CDR serialization, RTPS message building/parsing, SPDP discovery, and the beginnings of SEDP.

Three hours later, by 7:55 PM, Stage 6e was committed: 7,600 additional lines covering data pub/sub, the Rust participant implementation, hello_pub/hello_sub examples, RTI interop test infrastructure, and wire compatibility tests. The agent had gone from zero to a DDS implementation with working self-discovery and data exchange in a single afternoon session.

```
Jan 28 16:50  Initial commit: Python + Rust libraries, specs     98,767 lines
Jan 28 19:00  README                                                 139 lines
Jan 28 19:55  Stage 6e: Data pub/sub + RTI interop improvements    7,625 lines
```

By the end of the first day, VibeDDS could discover itself, exchange endpoint metadata, and publish/subscribe data between its own instances. The next challenge was making RTI Connext accept it as a peer.

## Day 2: the interop wall (January 29)

RTI's `rtiddsspy` tool could see VibeDDS's published data. VibeDDS to RTI worked. But the reverse direction — RTI publishing data that VibeDDS could receive — was completely broken. RTI reported **zero matched subscriptions**. It could see VibeDDS's reader in SEDP discovery but refused to send data to it.

The agent spent the day systematically attacking the problem. Two commits show the progression:

```
Jan 29 08:59  Enhance SEDP for RTI interop - QoS PIDs              1,451 lines
Jan 29 15:28  Document interop progress and add tooling             4,313 lines
```

The agent tried six different SEDP configurations, varying which QoS parameters were included, how XTypes metadata was formatted, and which type information blobs were sent. It captured pcap traces of RTI-to-RTI traffic and compared them byte-by-byte with VibeDDS-to-RTI traffic. It built diagnostic tools — an SEDP sniffer, a metatraffic analyzer, a matching diagnostic — that could interrogate RTI's internal state.

All six configurations failed identically. RTI still showed 0 matched subscriptions.

This is where we got stuck.

## The gap: January 29 to February 5

The git log tells the real story: zero commits for an entire week. The project was stuck, and rather than throw more hours at it, it simply sat idle. Both Claude (Opus 4.5) and GPT-5.2 (via Codex) had been pointed at the problem during CKO. The agent sessions explored increasingly exotic hypotheses:

- Maybe RTI required specific vendor PIDs (proprietary parameter IDs that RTI includes in its own traffic)?
- Maybe the TypeObject blob needed to be zlib-compressed in a specific way?
- Maybe the TypeConsistency encoding needed to use RTI's compact 8-byte format instead of the full XTypes struct?

None of these were the problem. The agents were searching in the wrong layer entirely. They were debugging the *content* of SEDP messages when the actual bug was that SEDP messages weren't *arriving*.

The interop-experiments log from January 29 captures the state of the investigation:

> *"SEDP discovery occurs, but RTI still does not match the VibeDDS reader for user data flow. Likely missing requirement is TypeInformation/TypeObject or an RTI-specific vendor PID needed for matching."*

This was completely wrong. The content was fine. The transport was broken.

## February 6: Opus 4.6 breaks through

On February 5, Anthropic released Claude Opus 4.6. The next morning, February 6, a fresh session was started on the RTI interop problem.

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

**Human involvement estimate:** 4-5 hours of active guidance out of ~11.5 hours of total development time. The human wrote zero lines of code. The human's role was architect, domain expert, and occasionally the voice saying "you're looking in the wrong place."

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
