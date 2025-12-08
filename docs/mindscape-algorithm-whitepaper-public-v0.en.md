# Mindscape Algorithm Technical Whitepaper

**Version**: v0.9 (Draft)
**Date**: 2025-12-05
**Maintainer**: Mindscape AI Development Team
**Status**: Technical Whitepaper (Public Edition)

> **Note**: This document is a technical whitepaper on the Mindscape Algorithm, intended for developers, researchers, and partners who wish to understand the architectural design philosophy of Mindscape AI. Some theoretical alignments (e.g., Active Inference, variational inference mechanisms) are currently design inspirations and future research directions, and have not been fully implemented at the code level.

---

## Executive Summary

The Mindscape Algorithm is the core architectural philosophy behind Mindscape AI. It organizes users' long-term intentions, project storylines, and creative themes into a governable, navigable cognitive space, and builds upon this foundation a comprehensive framework for intent governance and execution in LLM Agents.

This document systematically elaborates on the design philosophy of the Mindscape Algorithm from both theoretical foundations and architectural design perspectives, aligning with existing cognitive science and AI architecture research, providing a reference architectural blueprint for developers and teams who wish to adopt Mindscape AI in practice.

---

## Table of Contents

1. [Theoretical Foundations](#i-theoretical-foundations)
   - [1.1 Conceptual Spaces and Cognitive Maps](#11-conceptual-spaces-and-cognitive-maps)
   - [1.2 BDI Architecture and Hierarchical Reinforcement Learning](#12-bdi-architecture-and-hierarchical-reinforcement-learning)
   - [1.3 Active Inference and the Free Energy Principle](#13-active-inference-and-the-free-energy-principle)
   - [1.4 Modern LLM Agent Architecture Context](#14-modern-llm-agent-architecture-context)

2. [Architectural Design](#ii-architectural-design)
   - [2.1 Three-Layer Mindscape Model](#21-three-layer-mindscape-model)
   - [2.2 Intent Layer: Intent Governance](#22-intent-layer-intent-governance)
   - [2.3 Execution Layer and Semantic Engine](#23-execution-layer-and-semantic-engine)
   - [2.4 Bidirectional Data Flow and Integration Patterns](#24-bidirectional-data-flow-and-integration-patterns)

3. [Technical Alignment and Positioning](#iii-technical-alignment-and-positioning)
   - [3.1 Theoretical Alignment Summary](#31-theoretical-alignment-summary)
   - [3.2 Architectural Alignment Summary](#32-architectural-alignment-summary)
   - [3.3 Product Context and Application Scenarios](#33-product-context-and-application-scenarios)

4. [Future Directions](#iv-future-directions)

5. [References](#v-references)

6. [Appendix](#appendix)
   - [A. Glossary](#a-glossary)
   - [B. Architecture Diagrams](#b-architecture-diagrams)

---

## I. Theoretical Foundations

### 1.1 Conceptual Spaces and Cognitive Maps

#### 1.1.1 Conceptual Spaces Theory

**Theoretical Source**: Peter Gärdenfors' Conceptual Spaces theory (Gärdenfors, 2000, 2014)

**Core Propositions**:
- The mind organizes experience in a "spatialized" manner, rather than storing it solely as symbols or pure vectors
- Concepts are viewed as regions in multidimensional "quality dimensions"
  - Example: Color concepts as regions in "hue-brightness-saturation" space
  - Example: Taste concepts as distributions across dimensions such as sweet, sour, bitter, salty, umami
- Geometric distance between concepts directly represents semantic similarity
- The size and boundaries of regions reflect the scope and fuzziness of concepts

**Mapping to the Mindscape Algorithm**:

```
Conceptual Space (Theory)
    ↓
Intent Conceptual Space (Implementation)
    ├─ IntentCard: Nodes in space (specific goals/projects)
    ├─ IntentCluster: Semantic regions in space (theme lines/project lines)
    └─ Geometric distance → Semantic similarity → Intent governance engine judgment basis
```

**Architectural Correspondences**:
- **IntentCard** serves as nodes in space, with each card representing a specific long-term goal or project
- **IntentCluster** serves as semantic regions in space, aggregating related IntentCards into theme lines
- **Embedding vectors** provide mathematical representations of quality dimensions, calculating concept distances through cosine similarity
- **Intent governance engine** performs "convergence and layout" operations on this space, deciding node creation, updates, and aggregation

#### 1.1.2 Cognitive Maps / Cognitive Graphs

**Theoretical Source**: Hippocampal cognitive map research (O'Keefe & Nadel, 1978; Bellmund et al., 2018)

**Core Findings**:
- The hippocampus not only creates navigation maps for physical space but also establishes cognitive maps for abstract spaces (social status, value, task structure)
- These cognitive maps / cognitive graphs are the foundation for human learning of new tasks, knowledge transfer, and flexible behavior
- Abstract cognitive maps have structural properties similar to spatial navigation: path planning, distance calculation, regional division

**Mapping to the Mindscape Algorithm**:

```
Cognitive Map (Theory)
    ↓
Intent Cognitive Map (Implementation)
    ├─ Multiple Workspaces correspond to multiple "task spaces"
    ├─ IntentCluster as "regional divisions"
    ├─ Execution decision pipeline as "path planning"
    └─ Semantic execution engine as "local navigation engine"
```

**Architectural Correspondences**:
- **Mindscape** = User's Intent Cognitive Map, recording all long-term goals and project storylines
- **IntentCluster** = "Blocks / subgraphs" on the map, aggregating related intents into theme lines
- **Semantic execution engine** = Engine that dynamically calculates local regions and paths on this map
- **Workspace** = Multiple AI members navigating on the same cognitive map, rather than starting from scratch each time

**Theoretical Citations**:
- Gärdenfors, P. (2000). *Conceptual spaces: The geometry of thought*. MIT Press.
- Gärdenfors, P. (2014). *The geometry of meaning: Semantics based on conceptual spaces*. MIT Press.
- Bellmund, J. L. S., Gärdenfors, P., Moser, E. I., & Doeller, C. F. (2018). Navigating cognition: Spatial codes for human thinking. *Science*, 362(6415).

---

### 1.2 BDI Architecture and Hierarchical Reinforcement Learning

#### 1.2.1 BDI Architecture: Belief-Desire-Intention

**Theoretical Source**: BDI (Belief-Desire-Intention) Agent architecture (Bratman, 1987; Rao & Georgeff, 1995)

**Core Framework**:
- **Beliefs**: Agent's understanding of the world, including facts, states, and historical records
- **Desires**: Set of goals the agent wants to achieve, which may conflict or be incomplete
- **Intentions**: Subset of goals selected from Desires and committed to, representing actual plans to execute

**Key Design Principles**:
- "Selecting a plan" and "executing a plan" are separate activities
- Intentions have persistence; once committed, they continue execution until achieved or failed
- Need to select limited Intentions from numerous Desires under resource constraints

**Mapping to the Mindscape Algorithm**:

```
BDI Architecture (Theory)
    ↓
Intent Layer (Implementation)
    ├─ Beliefs ≈ Workspace memory, event history, semantic features
    ├─ Desires ≈ IntentSignal (candidate intent set)
    ├─ Intentions ≈ IntentCard (confirmed intents)
    └─ Plan Execution ≈ Playbook runtime / Semantic execution engine
```

**Architectural Correspondences**:
- **Beliefs**:
  - Event Layer records all message/tool/playbook history
  - Memory/Embedding Layer stores stable outcomes and important content
  - Semantic execution engine provides semantic features

- **Desires**:
  - IntentSignal represents candidate intents
  - Allows large quantities, fragmentation, purely internal use

- **Intentions**:
  - IntentCard represents confirmed and committed long-term goals
  - Quantity is controlled to ensure stable system operation

- **Plan Execution**:
  - Execution decision pipeline decides "whether to start playbook"
  - Playbook runtime / Semantic execution engine handles specific execution

**Theoretical Citations**:
- Bratman, M. E. (1987). *Intention, plans, and practical reason*. Harvard University Press.
- Rao, A. S., & Georgeff, M. P. (1995). BDI agents: From theory to practice. *ICMAS*, 95, 312-319.

#### 1.2.2 Hierarchical RL & Options Framework

**Theoretical Source**: Hierarchical Reinforcement Learning and Options Framework (Sutton et al., 1999; Bacon et al., 2017)

**Core Framework**:
- **Primitive Actions**: Lowest-level single-step actions
- **Options**: High-level actions with initiation/termination conditions, expandable into multi-step behavior sequences
- **Hierarchical Policy**:
  - High-level policy (meta-controller) selects which option to execute
  - Low-level policy (option internal policy) handles action sequences within the option

**Key Advantages**:
- Solves long-term goal and sparse reward problems
- Achieves behavior abstraction and reuse
- Supports knowledge transfer across tasks

**Mapping to the Mindscape Algorithm**:

```
Hierarchical RL / Options (Theory)
    ↓
Intent Layer Architecture (Implementation)
    ├─ High-level Policy ≈ Intent governance engine / Execution decision pipeline
    ├─ Options ≈ Playbooks (high-level behavior templates)
    ├─ Option Selection ≈ Deciding which Playbook to start
    └─ Low-level Policy ≈ Semantic execution engine / Playbook runtime
```

**Architectural Correspondences**:
- **High-level Policy**:
  - Intent governance engine decides which IntentSignals should be upgraded to IntentCards (intent governance)
  - Execution decision pipeline decides whether to start playbook (execution decision)

- **Options**:
  - Playbooks serve as high-level behavior templates, corresponding to specific task domains (grant proposal writing, course creation, etc.)
  - Each Playbook can expand into multi-step tool calls and agent interactions

- **Low-level Policy**:
  - Semantic execution engine serves as execution cluster, responsible for semantic understanding, RAG, and agent execution
  - Playbook runtime handles specific step execution and state management

**Theoretical Citations**:
- Sutton, R. S., Precup, D., & Singh, S. (1999). Between MDPs and semi-MDPs: A framework for temporal abstraction in reinforcement learning. *Artificial intelligence*, 112(1-2), 181-211.
- Bacon, P. L., Harb, J., & Precup, D. (2017). The option-critic architecture. *AAAI*, 31(1).

---

### 1.3 Active Inference and the Free Energy Principle

#### 1.3.1 Free Energy Principle

**Theoretical Source**: Karl Friston's Free Energy Principle (Friston, 2010)

**Core Propositions**:
- Organisms (including the brain) tend to choose states that reduce "surprise/uncertainty"
- Equivalent to performing variational Bayesian inference, continuously adjusting internal models and behavior to minimize prediction error
- "Free energy" serves as a variational bound, simultaneously covering perception and action

**Key Mechanisms**:
- **Generative Model**: The brain maintains an internal model of the world
- **Variational Inference**: Minimizes prediction error by adjusting internal states
- **Preferred States**: Defines states the agent wants to be in and states to avoid

#### 1.3.2 Active Inference

**Core Framework**:
- Views behavior, perception, and learning as processes of "minimizing variational free energy under a generative model"
- Replaces traditional RL rewards with prior preferences (priors on preferred states)
- Agent behavior balances between "actively collecting information" and "maintaining preferred states"

**Mapping to the Mindscape Algorithm**:

```
Active Inference (Theory)
    ↓
Mindscape Algorithm (Implementation)
    ├─ Preferred States ≈ Long-term intent preference distribution (IntentCard + IntentCluster)
    ├─ Generative Model ≈ Workspace's understanding of the world (Event + Memory Layer)
    ├─ Variational Inference ≈ Intent governance engine's convergence and layout
    └─ Action Selection ≈ Execution decision pipeline + Playbook execution
```

**Architectural Correspondences**:
- **Preferred States**:
  - IntentCard represents user's long-term preferences and goals
  - IntentCluster defines preference distributions for "theme lines / project lines"
  - These preference states continuously update, reflecting the evolution of user intentions

- **Generative Model**:
  - Event Layer records world state (conversations, tool calls, playbook execution)
  - Memory/Embedding Layer provides long-term memory and semantic representations
  - Semantic execution engine provides real-time semantic understanding and clustering

- **Variational Inference**:
  - Intent governance engine analyzes each conversation round, judging which IntentSignals should be upgraded to IntentCards
  - Uses semantic clustering features to improve judgment accuracy
  - Balances between "reducing chaos" and "maintaining preferred states"

- **Action Selection**:
  - Execution decision pipeline decides whether to start playbook (reducing prediction error)
  - Playbook / Semantic execution engine executes specific actions, collects information, and advances goals

**Theoretical Citations**:
- Friston, K. (2010). The free-energy principle: a unified brain theory? *Nature reviews neuroscience*, 11(2), 127-138.
- Friston, K., FitzGerald, T., Rigoli, F., Schwartenbeck, P., & Pezzulo, G. (2017). Active inference: a process theory. *Neural computation*, 29(1), 1-49.

---

### 1.4 Modern LLM Agent Architecture Context

#### 1.4.1 Standard LLM Agent Architecture

**Current Trends**: Planning + Memory + Tool Use + Environment Interaction

**Core Components**:
- **Planning**: Decides what to do next (e.g., ReAct, Plan-and-Solve)
- **Memory**: Long-term memory storage and retrieval (e.g., vector database, reflection)
- **Tool Use**: Calls external tools and APIs
- **Environment Interaction**: Interacts with external environment, obtains feedback

**Existing Architecture Examples**:
- **Generative Agents** (Park et al., 2023): LLM + long-term memory + reflection to simulate daily behavior in virtual towns
- **AutoGPT / BabyAGI**: General agent frameworks combining planning, memory, and tool use
- **LangChain / LlamaIndex**: Provide standard abstractions for Memory, Tool, and Agent

#### 1.4.2 Current Pain Points

**Problem 1: Memory Explosion, Lack of Governance**
- Vector databases become huge dumping grounds without clear governance strategies
- Lack of judgment mechanisms for "which memories are important, which can be discarded"

**Problem 2: Lack of Clear Goal / Intent Layer**
- Planner struggles to align "what's happening today" with "long-term projects"
- No clear intent governance layer, leading to fragmented behavior

**Problem 3: Execution and Governance Coupling**
- Semantic understanding, execution, and intent governance are mixed together, making extension and optimization difficult

#### 1.4.3 Positioning of the Mindscape Algorithm

**Core Proposition**:

> The Mindscape Algorithm = An additional "Intent-aware Cognitive Map" layer we add to LLM-Agents, responsible for managing goals, project storylines, and memory, and driving all underlying semantic clustering, RAG, Playbooks, and tool calls.

**Enhancement to Standard Architecture**:

```
Standard LLM Agent Architecture
    ├─ Planning
    ├─ Memory
    ├─ Tool Use
    └─ Environment Interaction

Mindscape Algorithm Enhancement
    ├─ Intent Governance Layer (New)
    │   ├─ IntentSignal → IntentCard lifecycle management
    │   ├─ IntentCluster theme line aggregation
    │   └─ Intent governance engine automatic convergence and layout
    ├─ Cognitive Map Layer (New)
    │   ├─ Intent Cognitive Space (Conceptual Space)
    │   ├─ Intent Cognitive Map (Cognitive Maps)
    │   └─ Preferred States Distribution (Active Inference)
    └─ Driving Standard Components
        ├─ Planning: Execution decision pipeline decides whether to start playbook
        ├─ Memory: Episode Memory selects high-value content based on IntentCluster
        ├─ Tool Use: Playbook defines tool call sequences
        └─ Environment: Semantic execution engine performs semantic understanding and agent tasks
```

**Theoretical Citations**:
- Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. *arXiv preprint arXiv:2304.03442*.
- Weng, L. (2023). LLM-powered autonomous agents. *Lil'Log*. https://lilianweng.github.io/posts/2023-06-23-agent/

---

## II. Architectural Design

### 2.1 Three-Layer Mindscape Model

#### 2.1.1 Overall Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│            Three-Layer Mindscape Algorithm Architecture      │
└─────────────────────────────────────────────────────────────┘

Layer 0: Signal Collector (Telemetry Layer)
├─ Intent Extractor (extracts intent signals from conversations, files, tool outputs)
├─ Multi-source Signal Collection (supports multiple signal sources)
└─ Output: IntentSignal
    └─ Allows large quantities, fragmentation, purely internal use

           ↓ (after each conversation round)

Layer 1: Intent Steward LLM (Layout / Governance Layer)
├─ Intent Governance Engine
├─ Input:
│   ├─ Recent conversation history
│   ├─ Recent IntentSignals
│   ├─ Currently visible IntentCards
│   └─ Semantic clustering features
├─ Output: IntentLayoutPlan
│   ├─ Long-term intents (CREATE/UPDATE IntentCard)
│   ├─ Short-term tasks (write log only)
│   └─ Signal mapping (processing decision for each signal)
└─ Automatic trigger + automatic recording, no user confirmation required

           ↓ (periodic, cross-round/cross-day)

Layer 2: Embedding Clustering (Cluster / Theme Layer)
├─ Intent Clustering Service
├─ Calls semantic execution engine to perform clustering
├─ Output: IntentCluster
│   ├─ cluster label (LLM named)
│   ├─ cluster-level metadata
│   └─ Associated with IntentCard
└─ Corresponds to "Project / Theme" columns
```

#### 2.1.2 Three-Layer Correspondences

| Theoretical Level | Architectural Level | Core Components | Data Models |
|------------------|---------------------|-----------------|------------|
| **Signal Layer** | Layer 0: Signal Collector | Intent Extractor<br/>Semantic Seed Extractor | IntentSignal |
| **Layout Layer** | Layer 1: Intent Steward | Intent Governance Engine | IntentCard<br/>IntentLayoutPlan |
| **Cluster Layer** | Layer 2: Embedding Clustering | Intent Clustering Service<br/>Semantic Execution Engine | IntentCluster |

---

### 2.2 Intent Layer: Intent Governance

#### 2.2.1 Design Goals

**Core Problems**:
- IntentSignal explosion (each conversation round may generate dozens or hundreds of signals)
- IntentSignal granularity too fine, requiring user confirmation one by one, not feasible
- Lack of dedicated governance layer, unable to automatically converge and layout

**Solutions**:
- Acknowledge that IntentSignal explosion is reasonable and valuable, but downgrade to internal signals
- Introduce intent governance engine LLM as dedicated governance layer, responsible for convergence and layout
- Achieve automation: change from "requiring user confirmation one by one" to "automatic trigger + automatic recording"
- Establish semantic skeleton: Embedding clustering responsible for cross-round, cross-day Intent convergence

#### 2.2.2 Architectural Components

**Component 1: Intent Extractor**
- Extracts IntentSignals from conversation messages, file uploads, semantic seed tasks
- Creates IntentSignals as candidate intents
- Records metrics: number of IntentSignals per conversation round

**Component 2: Intent Governance Engine (Intent Steward Service)**
- Automatically analyzes after each conversation round, decides changes to Intent panel
- Two-stage processing:
  - Stage A: Heuristic + small model pre-screening (reduces signal volume)
  - Stage B: Large model intent governance (outputs IntentLayoutPlan)
- Uses semantic clustering features to improve judgment accuracy

**Component 3: Intent Clustering Service**
- Periodically clusters IntentCards (nightly / after completing major playbook)
- Calls semantic execution engine to execute clustering algorithm
- Generates cluster labels, writes back to IntentCard.metadata.cluster_id

**Component 4: Execution Decision Pipeline (Intent Pipeline)**
- Retains three-layer analysis logic
- Layer 1: Interaction Type (QA / START_PLAYBOOK / MANAGE_SETTINGS)
- Layer 2: Task Domain
- Layer 3: Playbook Selection + automatic playbook triggering
- **Separated from intent governance engine**: Execution decision pipeline is responsible for "whether to start playbook", intent governance engine is responsible for "Intent panel and long-term memory"

#### 2.2.3 Parallel Pipeline Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Two Parallel Pipelines                    │
└─────────────────────────────────────────────────────────────┘

Pipeline A: Action Decision Pipeline
├─ Execution decision pipeline analysis
│   ├─ Layer 1: Interaction Type
│   ├─ Layer 2: Task Domain
│   └─ Layer 3: Playbook Selection
├─ Answers: "Should we start a playbook? Which one?"
└─ Triggers playbook execution

Pipeline B: Intent Layout Pipeline
├─ Intent governance engine analysis
├─ Answers: "What changes does this conversation round cause to the Intent panel?"
├─ Manages:
│   ├─ Which themes should be upgraded to IntentCards
│   ├─ Which IntentCard status/progress should be updated
│   └─ Which themes are long-term projects vs short-term tasks
└─ Automatically updates IntentCards, writes to intent_logs

Both pipelines consume the same batch of events / signals, but outputs are completely different
```

---

### 2.3 Execution Layer and Semantic Engine

#### 2.3.1 Positioning and Responsibilities

**Positioning**: Execution cluster (Execution Layer)

**Core Responsibilities**:
- **Semantic Understanding**: Understands semantic meaning of user input
- **Content Clustering**: Performs semantic clustering analysis on content
- **Context Management**: Manages conversation context
- **Agent Execution**: Executes Agent tasks

**Architectural Characteristics**:
- **Stateless Execution**: Does not store configuration, depends on passed payload
- **Request-level Caching**: Uses request-scoped cache to optimize performance
- **Multi-turn Conversation Support**: Supports multi-turn call scenarios such as Agentic RAG

#### 2.3.2 Relationship with Intent Layer

**Separation of Responsibilities**:
- **Semantic Execution Engine**: Responsible for semantic computation (clustering, RAG, embedding)
- **Intent Layer**: Responsible for governance decisions (IntentCard creation/updates, lifecycle management)

**Integration Methods**:
- Through clear API interfaces and data formats, avoiding architectural coupling
- Supports bidirectional data flow: IntentCluster → Semantic execution engine (goal-oriented), Semantic execution engine → Intent governance engine (semantic features)

---

### 2.4 Bidirectional Data Flow and Integration Patterns

#### 2.4.1 Data Flow Directions

**Direction 1: IntentCluster → Semantic Execution Engine (Goal-Oriented)**
- IntentCluster serves as context gate, driving semantic execution engine's retrieval and clustering
- Improves retrieval precision, only retrieving content related to current IntentCluster
- Implementation: Combo A (IntentCluster-driven goal-oriented source selection)

**Direction 2: Semantic Execution Engine → Intent Governance Engine (Semantic Features)**
- Semantic execution engine's conversation clustering results serve as judgment basis for intent governance engine
- Improves IntentCard creation/update accuracy
- Implementation: Combo B (Semantic clusters as semantic feature providers for intent governance engine)

**Direction 3: Intent Layer ↔ Semantic Execution Engine (Physical Engine)**
- Intent Layer calls semantic execution engine to execute clustering algorithms
- Unifies all semantic clustering algorithm implementations
- Implementation: Combo C (Semantic execution engine as physical engine for IntentCluster)

**Direction 4: Semantic Execution Engine → Memory Layer (Long-term Memory Selection)**
- Uses semantic execution engine's episode clustering to decide long-term memory content
- Improves long-term memory quality
- Implementation: Combo D (Episode Cluster decides long-term memory content)

#### 2.4.2 Four Integration Patterns Overview

| Combo | Data Flow Direction | Core Value |
|-------|---------------------|------------|
| **Combo A** | IntentCluster → Semantic Execution Engine | Goal-oriented source selection, improves retrieval precision |
| **Combo B** | Semantic Execution Engine → Intent Governance Engine | Semantic features improve judgment accuracy |
| **Combo C** | Intent Layer ↔ Semantic Execution Engine | Unifies clustering algorithm implementation |
| **Combo D** | Semantic Execution Engine → Memory Layer | Improves long-term memory quality |

Detailed implementation and API specifications will be released when the public implementation / SDK is launched.

---

## III. Technical Alignment and Positioning

### 3.1 Theoretical Alignment Summary

#### 3.1.1 Conceptual Spaces + Cognitive Maps

**Theoretical Alignment**:
- Mindscape = Intent Conceptual Space, IntentCard is nodes in space, IntentCluster is semantic regions
- Mindscape Algorithm = A set of rules for governing intent nodes on conceptual space

**Architectural Alignment**:
- Mindscape = Intent Cognitive Map, recording all long-term goals and project storylines
- IntentCluster = "Blocks / subgraphs" on the map
- Semantic execution engine = Engine that dynamically calculates local regions and paths on this map

#### 3.1.2 BDI + Hierarchical RL

**Theoretical Alignment**:
- Beliefs ≈ Workspace memory, event history, semantic features
- Desires ≈ IntentSignal (candidate intent set)
- Intentions ≈ IntentCard (confirmed intents)

**Architectural Alignment**:
- Intent Layer = BDI-influenced intent governance layer
- Intent governance engine / Execution decision pipeline = High-level policy / meta-controller
- Semantic execution engine / Playbook execution = Low-level controller / option internal policy

#### 3.1.3 Active Inference / Free Energy Principle

**Theoretical Alignment**:
- The Mindscape Algorithm converges users' long-term preferences, creative axes, and life goals into a continuously updated "intent preference distribution"
- Workspace, Playbook, and semantic clusters continuously select the next "expected to reduce chaos and increase value" action through heuristics + LLM reasoning in this preference space

**Architectural Alignment**:
- Mindscape = A state space containing preferences, world model, and feasible actions
- Mindscape Algorithm = Making "active inference-like decisions" on this state space

#### 3.1.4 Modern LLM Agent Architecture

**Theoretical Alignment**:
- The Mindscape Algorithm = An additional "Intent-aware Cognitive Map" layer we add to LLM-Agents
- Responsible for managing goals, project storylines, and memory, and driving all underlying semantic clustering, RAG, Playbooks, and tool calls

**Architectural Alignment**:
- Intent Governance Layer (New): IntentSignal → IntentCard lifecycle management
- Cognitive Map Layer (New): Intent Cognitive Space, Intent Cognitive Map, Preferred States Distribution
- Driving Standard Components: Planning, Memory, Tool Use, Environment Interaction

---

### 3.2 Architectural Alignment Summary

#### 3.2.1 Three-Layer Architecture Correspondences

| Theoretical Level | Architectural Level | Core Components | Data Models |
|------------------|---------------------|-----------------|-------------|
| Conceptual Space | Intent Cognitive Space | IntentCard, IntentCluster | IntentCard, IntentCluster |
| Cognitive Map | Intent Cognitive Map | Intent Clustering Service | IntentCluster |
| BDI Intentions | Intent Governance | Intent Governance Engine | IntentCard |
| HRL Options | Playbook System | Execution Decision Pipeline, Playbook runtime | Playbook execution events |
| Active Inference | Preference Distribution | Intent Governance Engine + IntentCluster | IntentCard + IntentCluster |

#### 3.2.2 Two-Layer Execution Architecture

```
┌─────────────────────────────────────────────────────────────┐
│            Two-Layer Execution Architecture Correspondences  │
└─────────────────────────────────────────────────────────────┘

Upper Layer: Intent Governance Layer
├─ Intent Governance Engine: Intent governance and layout
├─ IntentCluster: Theme line aggregation
└─ Execution Decision Pipeline: Execution decisions (whether to start playbook)

Lower Layer: Semantic Execution Layer
├─ Semantic understanding and clustering
├─ RAG retrieval
├─ Agent execution
└─ Content analysis

Integration Points: Four Integration Patterns
├─ Combo A: IntentCluster → Semantic Execution Engine (Goal-oriented)
├─ Combo B: Semantic Execution Engine → Intent Governance Engine (Semantic features)
├─ Combo C: Intent Layer ↔ Semantic Execution Engine (Physical engine)
└─ Combo D: Semantic Execution Engine → Memory Layer (Long-term memory)
```

---

### 3.3 Product Context and Application Scenarios

#### 3.3.1 For Individual Creators / Educators

**Core Value**:
> The Mindscape Algorithm = A system that helps you organize "everything you want to do in life" into executable project storylines, combined with Playbook automation.

**Application Scenarios**:
- **Project Management**: Clustering scattered tasks and ideas into theme lines (e.g., multilingual projects, fundraising activities, etc.)
- **Automated Workflows**: Automatically executing repetitive tasks through Playbooks (e.g., proposal writing, content production, etc.)
- **Long-term Memory**: System automatically identifies and records important decision points and transitions

**Technical Highlights**:
- Intent governance engine automatically converges fragmented intents without requiring user confirmation one by one
- IntentCluster automatically clusters related projects, forming theme lines
- Semantic execution engine provides precise semantic understanding and content retrieval

#### 3.3.2 For Teams / Agencies

**Core Value**:
> The Mindscape Algorithm = A layer of observable, governable "collective intent map" above all team cases, processes, and clients, connecting multiple Agents, tools, and knowledge bases.

**Application Scenarios**:
- **Case Management**: Multiple cases automatically clustered into theme lines (e.g., "government grant proposals", "course development")
- **Team Collaboration**: Multiple Workspaces share the same Intent Cognitive Map
- **Knowledge Accumulation**: Important decisions and outcomes automatically written to long-term memory for future reference

**Technical Highlights**:
- Cross-Workspace IntentCluster aggregation
- Observability and governance capabilities of collective intents
- Multiple Agents collaborating and navigating on the same cognitive map

#### 3.3.3 For AI / Developer Community

**Core Value**:
> The Mindscape Algorithm = An intent-first LLM agent architecture that places current LLM agent's Planning/Memory/Tool usage into a framework with a clear mindscape model.

**Application Scenarios**:
- **Agent Architecture Design**: Provides Intent Governance Layer as a standard component
- **Memory Governance**: Solves the problem of vector databases becoming dumping grounds
- **Goal Alignment**: Solves the problem of Planner struggling to align "what's happening today" with "long-term projects"

**Technical Highlights**:
- Intent-aware Cognitive Map as a new architectural layer
- Clear theoretical alignment (Conceptual Spaces, BDI, Active Inference)
- Extensible integration patterns (Four Combos)

---

## IV. Future Directions

> **Important Note**: The following content belongs to research and exploration directions and does not represent formal product timeline commitments.

### 4.1 Theoretical Deepening

- **Variational Inference Implementation**: Implement Active Inference's variational inference mechanisms into the intent governance engine
- **Cognitive Map Visualization**: Generate visualizable cognitive maps based on IntentCluster
- **Cross-task Transfer**: Utilize IntentCluster to achieve cross-Workspace knowledge transfer

### 4.2 Architectural Optimization

- **Incremental Clustering**: Implement incremental IntentCluster updates to avoid full recomputation
- **Multimodal Support**: Incorporate images, audio, and other content into IntentSignal extraction
- **Distributed Architecture**: Support cross-machine Intent Cognitive Map sharing

### 4.3 Productization

- **Intent Panel UI**: Develop project panels based on IntentCluster
- **Batch Operations**: Support users to batch adjust or close IntentCards
- **Observability**: Provide visualization and auditing of Intent governance processes

---

## V. References

### Theoretical Literature

**Conceptual Spaces & Cognitive Maps**:
- Gärdenfors, P. (2000). *Conceptual spaces: The geometry of thought*. MIT Press.
- Gärdenfors, P. (2014). *The geometry of meaning: Semantics based on conceptual spaces*. MIT Press.
- Bellmund, J. L. S., Gärdenfors, P., Moser, E. I., & Doeller, C. F. (2018). Navigating cognition: Spatial codes for human thinking. *Science*, 362(6415).
- O'Keefe, J., & Nadel, L. (1978). *The hippocampus as a cognitive map*. Oxford University Press.

**BDI & Hierarchical RL**:
- Bratman, M. E. (1987). *Intention, plans, and practical reason*. Harvard University Press.
- Rao, A. S., & Georgeff, M. P. (1995). BDI agents: From theory to practice. *ICMAS*, 95, 312-319.
- Sutton, R. S., Precup, D., & Singh, S. (1999). Between MDPs and semi-MDPs: A framework for temporal abstraction in reinforcement learning. *Artificial intelligence*, 112(1-2), 181-211.
- Bacon, P. L., Harb, J., & Precup, D. (2017). The option-critic architecture. *AAAI*, 31(1).

**Active Inference & Free Energy**:
- Friston, K. (2010). The free-energy principle: a unified brain theory? *Nature reviews neuroscience*, 11(2), 127-138.
- Friston, K., FitzGerald, T., Rigoli, F., Schwartenbeck, P., & Pezzulo, G. (2017). Active inference: a process theory. *Neural computation*, 29(1), 1-49.

**Modern LLM Agents**:
- Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. *arXiv preprint arXiv:2304.03442*.
- Weng, L. (2023). LLM-powered autonomous agents. *Lil'Log*. https://lilianweng.github.io/posts/2023-06-23-agent/

---

## Appendix

### A. Glossary

| Term | English | Definition |
|------|---------|------------|
| 心智空間算法 | Mindscape Algorithm | Core architectural philosophy of Mindscape AI, organizing users' long-term intents into a governable cognitive space |
| IntentSignal | Intent Signal | Internal system signals representing possible intents, allowing large quantities and fragmentation |
| IntentCard | Intent Card | User-visible project/long-term goal nodes, confirmed and committed intents |
| IntentCluster | Intent Cluster | Semantic regions that aggregate related IntentCards into theme lines/project lines |
| IntentSteward | Intent Steward | Dedicated LLM responsible for intent convergence and layout, deciding which IntentSignals should be upgraded to IntentCards |
| Conceptual Space | Conceptual Space | Gärdenfors' theory, viewing concepts as regions in multidimensional quality dimensions |
| Cognitive Map | Cognitive Map | Cognitive maps established by the hippocampus for abstract spaces (task structure, value) |
| BDI | Belief-Desire-Intention | Traditional AI agent architecture, splitting agent internal state into beliefs, desires, and intentions |
| Active Inference | Active Inference | Viewing behavior, perception, and learning as processes of minimizing variational free energy |

### B. Architecture Diagrams

(See relevant sections in main text)

---

**Last Updated**: 2025-12-05
**Maintainer**: Mindscape AI Development Team
**Status**: Technical Whitepaper v0.9 (Public Edition)


