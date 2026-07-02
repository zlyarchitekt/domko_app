---
source: https://www.youtube.com/watch?v=TxQ_o-ycNTs
title: Finch Webinar April 7
duration: 50:48
watched_at: 2026-07-02T10:08:56.363015+02:00
intent: detailed app mechanics for building replica
hero_frames: [frame_0001.jpg, frame_0011.jpg, frame_0021.jpg, frame_0025.jpg, frame_0031.jpg]
transcript_source: captions
---

# Finch Webinar April 7

## TL;DR

- Finch 3D uses a cloud-first geometry engine with direct CAD/BIM integrations (Rhino, Grasshopper, Revit, Archicad, Forma) to automate space planning.
- Core mechanics include rule-based circulation and vertical cores layout, unit mix optimization with grid-snapping trades, and constraint-based adaptive floor plans.
- Revit/Archicad integrations reconstruct geometric objects natively (using CAD native classes like walls/doors/families) instead of static imports.
- Includes an AI compliance assistant ("Archie") that edits elements across multiple units using natural language instructions.

## Key moments

- **[02:18] Principles** — Explanation of three core pillars: Interoperability, Automation, Customization.
- **[05:32] KPF Workshop** — Visualizing the Grasshopper workflow for subdividing a massive 17-plot site.
- **[15:00] Browser Demo** — Jesper shows the Finch web UI, editing story programs and real-time GFA/GIA schedules.
- **[16:43] Core & Circulation Generation** — Generating cores and corridors with instant egress distance validations.
- **[18:15] Unit Mix Generation** — Distributing apartment targets and snapping them to structural grid lines.
- **[21:30] Adaptive Floor Plans** — Demonstration of the "Intent Layer" library, defining flexible/rigid walls and corridor constraints.
- **[23:34] Plan Copy-Paste** — Copying layout plans across units with automatic corridor alignment rotation.
- **[25:15] Archie AI** — The pocket door offset constraint adjustment across hundreds of units simultaneously.
- **[27:00] Revit/Archicad Reconstruction** — Amelia demonstrates the native reconstruction of families, groups, and direct generation in Revit/Archicad.

## Hook microscope (0-10s)

- Frames: 20 at 2 fps

- **[00:00 - 00:03]** Title card/intro.
- **[00:03 - 00:10]** CEO Pamela welcomes the audience, introducing founders and CPO Jesper. The hook pattern is a standard webinar intro with a quick transition to the value proposition.

## Editorial profile

- Shots: 50
- Cuts/min: 0.98
- Mean shot length: 60.96s
- Median shot length: 27.68s
- Talking-head ratio: n/a (opencv not installed)

- Technical product webinar, UI screencasts, split screens showing Rhino/Finch/Revit side-by-side.

## Quotable moments

- **[03:24]** "making the shift from craftsman to curator."
- **[08:39]** "value here as an architect is not about drawing floor plans faster anymore, but choosing better for your project."
- **[12:08]** "seeing this kind of big project being built automatically in Revit is very inspiring."

## Entities mentioned

- People: [[pamela-nunez-wallgren]], [[jesper-wallgren]], [[amelia-henry]]
- Companies: Finch, KPF, Autodesk
- Tools / products: Revit, Archicad, Rhino, Grasshopper, Autodesk Forma, Archie
- Places: London, Sweden, New York

## Concepts surfaced

- Space planning automation: algorithmic generation of rooms and spaces inside building volumes.
- Constraint-based parametric design: definition of flexible/rigid walls and spaces using geometric Solvers.
- Native BIM geometry reconstruction: API-based conversion of web geometries into native CAD families/classes.
- Automated egress pathfinding: real-time calculation of fire escape paths and core optimization.

## Transcript

_Source: captions._

```
[00:03] Hi everyone, and welcome to today's webinar. My name is Pamela. I'm one of
[00:06] webinar. My name is Pamela. I'm one of the founders and CEO here at Finch.
[00:08] the founders and CEO here at Finch. I'm here together with Jesper Wallgren,
[00:11] I'm here together with Jesper Wallgren, also a founder and CPO, and Amelia
[00:14] also a founder and CPO, and Amelia Henry, who is a senior partnership lead.
[00:17] Henry, who is a senior partnership lead. We are all have a background as
[00:19] We are all have a background as architects and are working today at
[00:21] architects and are working today at Finch.
[00:22] Finch. So, today's session is about
[00:30] how the shift the shift that is happening in our industry, how workflows
[00:32] happening in our industry, how workflows are changing, and how the role of the
[00:34] are changing, and how the role of the architect is evolving from producing
[00:37] architect is evolving from producing solutions to to directing them.
[00:40] solutions to to directing them. And as more of you adopt these tools,
[00:42] And as more of you adopt these tools, the bottlenecks and competitive edge
[00:44] the bottlenecks and competitive edge would no longer be around production. It
[00:46] would no longer be around production. It will be around decision-making, and we
[00:49] will be around decision-making, and we will explore this through a workshop
[00:51] will explore this through a workshop that we recently hosted together with
[00:53] that we recently hosted together with KPF for the ATM Summit build-up.
[00:56] KPF for the ATM Summit build-up. But first, let me take you back to why
[00:59] But first, let me take you back to why we started Finch. So, Jesper and I were
[01:02] we started Finch. So, Jesper and I were in this call are both architects. We
[01:04] in this call are both architects. We used to run our own architecture
[01:05] used to run our own architecture company.
[01:06] company. We felt the frustration with the current
[01:09] We felt the frustration with the current CAD and BIM solutions that perhaps you
[01:11] CAD and BIM solutions that perhaps you were feeling as well. We were wanting to
[01:13] were feeling as well. We were wanting to spend to spend more time designing
[01:16] spend to spend more time designing architecture,
[01:17] architecture, but we found ourselves with a lot of
[01:20] but we found ourselves with a lot of manual repetitive work and less time in
[01:23] manual repetitive work and less time in designing. So, we developed a lot of our
[01:26] designing. So, we developed a lot of our own in-house tools
[01:27] own in-house tools to make to become more competitive
[01:29] to make to become more competitive essentially.
[01:31] essentially. And some of these tools were posted
[01:33] And some of these tools were posted online, and it turned out that there
[01:35] online, and it turned out that there were many many more out there who shared
[01:37] were many many more out there who shared this frustration.
[01:39] this frustration. So, we understood
[01:41] So, we understood with this adaptive plan that we could
[01:43] with this adaptive plan that we could make a bigger impact on the world of
[01:45] make a bigger impact on the world of architecture by providing our industry
[01:47] architecture by providing our industry peers with better software.
[01:49] peers with better software. So, we folded architecture firm and
[01:52] So, we folded architecture firm and stayed started Finch with one clear
[01:54] stayed started Finch with one clear mission.
[01:55] mission. To build the tool that we had needed
[01:57] To build the tool that we had needed ourselves as architects.
[01:59] ourselves as architects. We want to move from manually producing
[02:01] We want to move from manually producing drawings to directing design outcomes.
[02:06] drawings to directing design outcomes. And we wanted to
[02:09] And we wanted to make sure
[02:10] make sure that
[02:12] that Oh, sorry. [clears throat]
[02:14] Oh, sorry. [clears throat] And this is why we built Finch around
[02:16] And this is why we built Finch around these three principles. So,
[02:19] these three principles. So, interoperability, automation, and
[02:21] interoperability, automation, and customization. Not as features, but as
[02:24] customization. Not as features, but as enablers of this shift.
[02:26] enablers of this shift. So, if we start with interoperability,
[02:28] So, if we start with interoperability, for us this meant staying within our
[02:30] for us this meant staying within our familiar environment, working seamlessly
[02:32] familiar environment, working seamlessly with the tools that we were already
[02:33] with the tools that we were already using, making it easy to adopt and
[02:36] using, making it easy to adopt and integrate.
[02:37] integrate. When we think about automation, we saw
[02:39] When we think about automation, we saw that our client briefs were getting
[02:41] that our client briefs were getting longer and longer, and the expected
[02:42] longer and longer, and the expected turnaround time was getting shorter. We
[02:45] turnaround time was getting shorter. We want to build a solution that allowed us
[02:47] want to build a solution that allowed us to explore more options deeper and
[02:49] to explore more options deeper and faster, but without sacrificing
[02:52] faster, but without sacrificing precision or design quality.
[02:54] precision or design quality. And the final one, when it comes to
[02:56] And the final one, when it comes to customization, we understand that every
[02:58] customization, we understand that every project is unique. And all of you here
[03:01] project is unique. And all of you here today have a unique approach of how to
[03:03] today have a unique approach of how to solve a certain specific site.
[03:06] solve a certain specific site. So, we want to make sure that you could
[03:08] So, we want to make sure that you could learn from past projects and embed
[03:10] learn from past projects and embed knowledge knowledge and design systems
[03:12] knowledge knowledge and design systems to steer the generated results.
[03:15] to steer the generated results. And we still live by these principles
[03:17] And we still live by these principles that allows you to define intent,
[03:19] that allows you to define intent, explore at scale, and stay in control,
[03:22] explore at scale, and stay in control, making the shift from craftsman to
[03:24] making the shift from craftsman to curator.
[03:30] And Finch is already being used by leading architecture firms from all
[03:32] leading architecture firms from all around the world. We have a waiting list
[03:34] around the world. We have a waiting list of more than 100,000 people, but we are
[03:37] of more than 100,000 people, but we are partnering with architecture firms
[03:39] partnering with architecture firms approximately six per month to make sure
[03:41] approximately six per month to make sure that we
[03:43] that we can support them in their projects.
[03:46] can support them in their projects. We're very hands-on with our partners.
[03:48] We're very hands-on with our partners. So, if you're interested in becoming one
[03:49] So, if you're interested in becoming one of our partners, reach out to us after
[03:51] of our partners, reach out to us after the webinar.
[03:56] But we will have a look at what the workflow that I just described looks
[03:58] workflow that I just described looks like in practice. We'll show a demo from
[04:00] like in practice. We'll show a demo from our workshop that we did with KPF, where
[04:03] our workshop that we did with KPF, where we demonstrated a connected
[04:04] we demonstrated a connected computational workflow from urban master
[04:06] computational workflow from urban master planning to BIM-ready floor plans.
[04:09] planning to BIM-ready floor plans. In just 2 hours, we developed an
[04:11] In just 2 hours, we developed an optimized unit mix for eight more than
[04:13] optimized unit mix for eight more than 800 units. We generated floor plans and
[04:16] 800 units. We generated floor plans and brought everything into Revit as fully
[04:18] brought everything into Revit as fully structured BIM geometry.
[04:20] structured BIM geometry. This was work that would have normally
[04:21] This was work that would have normally taken weeks. Well, this was done in only
[04:24] taken weeks. Well, this was done in only 2 hours.
[04:25] 2 hours. So, with that, I will hand it over to
[04:27] So, with that, I will hand it over to Jesper, who will walk you through this
[04:29] Jesper, who will walk you through this workflow and what it looks like.
[04:32] workflow and what it looks like. Thank you. So, let me share my screen to
[04:35] Thank you. So, let me share my screen to start with.
[04:42] There we go. Yes, so this was a workshop at the ATM
[04:45] Yes, so this was a workshop at the ATM Summit in London we did together with
[04:48] Summit in London we did together with KPF, and I'm going to go through the
[04:50] KPF, and I'm going to go through the work flow we created here together with
[04:53] work flow we created here together with KPF and how we went from a site into a
[04:55] KPF and how we went from a site into a fully BIM model. And while doing so,
[04:58] fully BIM model. And while doing so, we're going to have a look at how the
[05:00] we're going to have a look at how the role of the architect is changing from
[05:02] role of the architect is changing from craftsman to more of a curating role.
[05:06] craftsman to more of a curating role. After we go through this
[05:08] After we go through this webinar or the workshop we did with KPF,
[05:11] webinar or the workshop we did with KPF, I'm also going to do a live demo of
[05:13] I'm also going to do a live demo of roughly the same same flow just to give
[05:17] roughly the same same flow just to give you a
[05:18] you a sneak peek more in-depth of how how
[05:20] sneak peek more in-depth of how how software works.
[05:23] software works. Okay.
[05:24] Okay. But let's
[05:26] But let's start here. So, the
[05:27] start here. So, the the workshop we did with KPF was divided
[05:29] the workshop we did with KPF was divided into two parts. In the first part,
[05:32] into two parts. In the first part, Michael from KPF started with setting up
[05:34] Michael from KPF started with setting up a Grasshopper script for a massive site.
[05:39] a Grasshopper script for a massive site. It was a really big one. He subdivided
[05:41] It was a really big one. He subdivided into 17 plots, and then
[05:45] into 17 plots, and then we detailed one of these plots further
[05:48] we detailed one of these plots further in Finch. And it is the second part of
[05:50] in Finch. And it is the second part of the workflow we're going to
[05:52] the workflow we're going to zoom into here.
[05:57] And just as Pamela mentioned, interoperability is a big part of Finch,
[06:00] interoperability is a big part of Finch, and we need to be where the user are.
[06:02] and we need to be where the user are. So, Michael was working in Grasshopper
[06:05] So, Michael was working in Grasshopper in this particular workshop. So, of
[06:08] in this particular workshop. So, of course, we have a native Grasshopper
[06:09] course, we have a native Grasshopper component that he used to send his
[06:12] component that he used to send his geometry into Finch. And this also
[06:15] geometry into Finch. And this also highlights the
[06:17] highlights the collaboration possibilities cuz cuz
[06:19] collaboration possibilities cuz cuz Michael was sitting in London,
[06:21] Michael was sitting in London, and I was sitting in Sweden Sweden
[06:24] and I was sitting in Sweden Sweden receiving his geometry live. So, a
[06:27] receiving his geometry live. So, a single source of truth in the cloud.
[06:33] And when I get the geometry into Finch, I
[06:36] when I get the geometry into Finch, I started to subdividing the building
[06:40] started to subdividing the building further. And we've all done it with
[06:43] further. And we've all done it with traditional methods. We draw up a
[06:47] traditional methods. We draw up a handful of suggestions,
[06:50] handful of suggestions, but instead here with new generative
[06:52] but instead here with new generative tools like Finch, the computer generates
[06:55] tools like Finch, the computer generates thousands for you, and you go from
[06:58] thousands for you, and you go from drawing three options manually to
[07:02] drawing three options manually to evaluating 30. And you change from
[07:05] evaluating 30. And you change from adjusting geometry to adjusting input
[07:08] adjusting geometry to adjusting input parameters and intent. So, the role is
[07:11] parameters and intent. So, the role is shifting from executing to deciding. So,
[07:15] shifting from executing to deciding. So, from craftsman to curator.
[07:23] And when we had this unit mix in place, we also had a look at the floor plan
[07:26] we also had a look at the floor plan library in Finch. And we will go through
[07:28] library in Finch. And we will go through this one more time in the live demo
[07:30] this one more time in the live demo later.
[07:32] later. The floor plan library is what we call
[07:34] The floor plan library is what we call the intent layer in Finch. And this is
[07:37] the intent layer in Finch. And this is where you describe for the system how
[07:39] where you describe for the system how you would like your design to behave.
[07:42] you would like your design to behave. And this becomes the foundation where
[07:44] And this becomes the foundation where you
[07:45] you generate from later on. And this is a
[07:47] generate from later on. And this is a great way of sharing knowledge, sharing
[07:49] great way of sharing knowledge, sharing designs within your firm. And this is
[07:52] designs within your firm. And this is also what makes the results you get
[07:55] also what makes the results you get different from from the next architect's
[07:57] different from from the next architect's results.
[08:04] Then we went back to our project and generated floor plans. And here the the
[08:08] generated floor plans. And here the the shift of the role becomes very clear.
[08:12] shift of the role becomes very clear. You tell Finch you want to generate
[08:14] You tell Finch you want to generate floor plans, and then you get results
[08:17] floor plans, and then you get results presented in three categories from your
[08:19] presented in three categories from your own library, from your organization
[08:21] own library, from your organization library, and Finch generated.
[08:24] library, and Finch generated. And and here it's not about drawing
[08:27] And and here it's not about drawing floor plans from scratch anymore, but
[08:30] floor plans from scratch anymore, but deciding what
[08:32] deciding what which one of these floor plans that fits
[08:33] which one of these floor plans that fits your project the best. And your main
[08:37] your project the best. And your main value here as an architect is not about
[08:39] value here as an architect is not about drawing floor plans faster anymore, but
[08:42] drawing floor plans faster anymore, but choosing better for your project.
[08:46] choosing better for your project. And um
[08:47] And um of course, Finch helps you to evaluate
[08:50] of course, Finch helps you to evaluate these results. But I think one one
[08:53] these results. But I think one one important thing to highlight here is
[08:55] important thing to highlight here is also since you once were or maybe still
[08:57] also since you once were or maybe still are a craftsman, you are also equipped
[09:01] are a craftsman, you are also equipped with
[09:02] with with the tools to choose which one of
[09:04] with the tools to choose which one of these plans is better for your project.
[09:14] The last thing we presented in Finch is our AI assistant called Archie.
[09:18] our AI assistant called Archie. The tools I've shown here
[09:20] The tools I've shown here up until now has been about creating
[09:22] up until now has been about creating geometry from zero to to one, creating
[09:25] geometry from zero to to one, creating new geometry. This is not what Archie
[09:29] new geometry. This is not what Archie is doing. Archie is more about getting
[09:31] is doing. Archie is more about getting things done. And the kind of tasks you
[09:34] things done. And the kind of tasks you can assign to Archie is to tell him to
[09:37] can assign to Archie is to tell him to to make sure that all of your doors are
[09:40] to make sure that all of your doors are placed 3 in from the wall, not 2 and
[09:43] placed 3 in from the wall, not 2 and 1/2, not 4. And then Archie gets to work
[09:46] 1/2, not 4. And then Archie gets to work and goes through hundreds of designs in
[09:48] and goes through hundreds of designs in your project here, make sure everything
[09:51] your project here, make sure everything follow whatever you have asked for
[09:54] follow whatever you have asked for him him to to check, and you can move on
[09:57] him him to to check, and you can move on to to other
[09:58] to to other bigger design challenges in your
[10:01] bigger design challenges in your project. So, this is
[10:02] project. So, this is great way of just, you know, get some
[10:06] great way of just, you know, get some assistance within within your design
[10:08] assistance within within your design flow.
[10:15] And when you have created all of this data in Finch, how do you get it out?
[10:17] data in Finch, how do you get it out? This is something that we thought about
[10:20] This is something that we thought about long and hard when designing our Revit
[10:23] long and hard when designing our Revit extension. And Amelia will go through
[10:27] extension. And Amelia will go through the Revit extension more in-depth later
[10:29] the Revit extension more in-depth later on.
[10:30] on. But,
[10:32] But, we we we thought about it. We talked to
[10:34] we we we thought about it. We talked to a lot of customers and one very common
[10:38] a lot of customers and one very common workflow when designing a project is
[10:40] workflow when designing a project is that you start in a design software such
[10:42] that you start in a design software such as
[10:42] as Rhino SketchUp, and then you simply
[10:45] Rhino SketchUp, and then you simply remodel your whole project in Archicad
[10:49] remodel your whole project in Archicad or Revit. And this kind of workflow has
[10:52] or Revit. And this kind of workflow has two consequences two main consequences,
[10:54] two consequences two main consequences, I would say. One one bad and one
[10:56] I would say. One one bad and one positive. Let's start with the
[10:58] positive. Let's start with the with the positive one, and
[11:01] with the positive one, and that is that when you remodel your
[11:03] that is that when you remodel your project in your BIM solution,
[11:06] project in your BIM solution, you get a clean slate, you know, start
[11:08] you get a clean slate, you know, start from scratch, but you also model it with
[11:10] from scratch, but you also model it with the native tools in Revit, which makes
[11:14] the native tools in Revit, which makes Revit works better, of course, than
[11:16] Revit works better, of course, than compared to if you import a lot of
[11:18] compared to if you import a lot of geometry. The the not so good thing
[11:20] geometry. The the not so good thing about this flow is, of course, that it
[11:21] about this flow is, of course, that it can be very frustrating to model your
[11:25] can be very frustrating to model your project all over again when you already
[11:28] project all over again when you already have done it once. So, this was
[11:30] have done it once. So, this was something that we considered, can we
[11:31] something that we considered, can we just take the good part when we're
[11:33] just take the good part when we're building our
[11:35] building our extension? It turns out that we can. So,
[11:38] extension? It turns out that we can. So, when you use the Revit extension or
[11:40] when you use the Revit extension or Archicad extension in Finch,
[11:43] Archicad extension in Finch, the extension looks at the Finch model,
[11:46] the extension looks at the Finch model, and then it actually rebuilds your whole
[11:49] and then it actually rebuilds your whole project with the native tools in Revit
[11:52] project with the native tools in Revit and Archicad. So, and you can map your
[11:55] and Archicad. So, and you can map your own families. So, the the the the model
[11:59] own families. So, the the the the model that's being built follows your design
[12:02] that's being built follows your design principle that you've set up in your
[12:04] principle that you've set up in your practice. And and seeing this kind of
[12:08] practice. And and seeing this kind of big project being built automatically in
[12:10] big project being built automatically in Revit is is
[12:11] Revit is is is very inspiring for everyone who has
[12:13] is very inspiring for everyone who has spent weeks setting up these models.
[12:20] So, that was the workshop with KPF.
[12:22] KPF. We will go through it in a live demo
[12:24] We will go through it in a live demo here soon.
[12:26] here soon. If you want to see the full workshop, it
[12:29] If you want to see the full workshop, it was a 4-hour-long workshop, you can
[12:31] was a 4-hour-long workshop, you can simply head into YouTube and search for
[12:34] simply head into YouTube and search for ATN Finch KPF, and
[12:37] ATN Finch KPF, and you will see it among top result there.
[12:45] Before we head into the live demo, let's wrap up the slides.
[12:47] wrap up the slides. So, a couple of words about 2026 and our
[12:51] So, a couple of words about 2026 and our road map.
[12:53] road map. We have been very residential heavy up
[12:56] We have been very residential heavy up until now. We're introducing more
[12:58] until now. We're introducing more typologies in Finch.
[13:00] typologies in Finch. We already started to launch a lot of
[13:02] We already started to launch a lot of office features, and in the pipeline
[13:05] office features, and in the pipeline later on is health care and educational
[13:07] later on is health care and educational buildings as well.
[13:09] buildings as well. We're also launching our own 3D editor.
[13:13] We're also launching our own 3D editor. As I
[13:15] As I showed here in the workflow, as
[13:17] showed here in the workflow, as we started in Grasshopper Rhino, and
[13:20] we started in Grasshopper Rhino, and then we went into Finch and worked with
[13:22] then we went into Finch and worked with the mass.
[13:24] the mass. When we're launching the 3D editor, you
[13:25] When we're launching the 3D editor, you will be able to start immediately or
[13:27] will be able to start immediately or directly in in Finch.
[13:30] directly in in Finch. And last thing is the documentation
[13:34] And last thing is the documentation part. We're developing document
[13:37] part. We're developing document documentation capabilities for schematic
[13:39] documentation capabilities for schematic design, so you will be able to stay
[13:42] design, so you will be able to stay longer in Finch before you head into
[13:45] longer in Finch before you head into Revit and Archicad.
[13:54] And maybe you would like to say a couple of words. I'm [snorts] allowed to wrap
[13:56] of words. I'm [snorts] allowed to wrap the presentation up here before we head
[13:59] the presentation up here before we head into the live demo.
[14:07] Nope. You got
[14:08] You got Sure.
[14:10] Sure. I mean, this is a presentation that we
[14:12] I mean, this is a presentation that we presented at the the ATN Summit. We're
[14:15] presented at the the ATN Summit. We're really excited about this shift that is
[14:17] really excited about this shift that is happening, and we, of course, want to
[14:19] happening, and we, of course, want to support as many of our industry peer
[14:22] support as many of our industry peer adapting to this new era of AI.
[14:26] adapting to this new era of AI. So, if you are interested in this type
[14:29] So, if you are interested in this type of workflow, if you see Finch as a
[14:32] of workflow, if you see Finch as a potential fit for the type of project
[14:33] potential fit for the type of project you work with, just reach out to you to
[14:36] you work with, just reach out to you to us. We will send out the an email
[14:38] us. We will send out the an email tomorrow with the with the link to the
[14:41] tomorrow with the with the link to the recording of the full webinar, and there
[14:43] recording of the full webinar, and there you have our contact information if you
[14:44] you have our contact information if you want to
[14:46] want to get in touch with us to learn more about
[14:47] get in touch with us to learn more about what that type of partnerships look
[14:49] what that type of partnerships look like.
[14:54] Okay, super. So, let's head into the live demo here.
[14:59] So, let's head into the live demo here. So,
[15:00] So, this is Finch. It runs in the browser.
[15:03] this is Finch. It runs in the browser. This is how it looks.
[15:05] This is how it looks. We're going to take this mass and
[15:07] We're going to take this mass and generate circulation, unit mix, and and
[15:11] generate circulation, unit mix, and and floor plans in it. And when I'm done
[15:13] floor plans in it. And when I'm done with it, Amelia will demonstrate the
[15:15] with it, Amelia will demonstrate the Revit plugin.
[15:17] Revit plugin. A couple of words about how I got this
[15:20] A couple of words about how I got this geometry into the browser. We connect to
[15:23] geometry into the browser. We connect to existing software.
[15:25] existing software. Just give me a second here. I'm going to
[15:28] Just give me a second here. I'm going to change my camera.
[15:31] change my camera. There we go. So, we connect to existing
[15:34] There we go. So, we connect to existing so
[15:35] so software. We connect to Rhino,
[15:37] software. We connect to Rhino, Grasshopper, Revit, Archicad, and
[15:39] Grasshopper, Revit, Archicad, and Formit. So, this is where you start your
[15:41] Formit. So, this is where you start your design process.
[15:43] design process. In this example, I'm going to show you
[15:45] In this example, I'm going to show you our Rhino extension. So, this is where
[15:47] our Rhino extension. So, this is where the
[15:49] the the geometry come. We have a Finch
[15:52] the geometry come. We have a Finch extension down here, and I've simply,
[15:54] extension down here, and I've simply, let's hide the context, uploaded my mass
[15:58] let's hide the context, uploaded my mass into Finch. And this is then where I'm
[16:01] into Finch. And this is then where I'm going to start detailing it further.
[16:08] There we go. And this is how it looks when you get into Finch. The first thing
[16:11] when you get into Finch. The first thing I'm going to start with is just
[16:12] I'm going to start with is just assigning some programs here. I simply
[16:15] assigning some programs here. I simply select the different stories. I say I
[16:18] select the different stories. I say I want residential. Let's put retail here
[16:20] want residential. Let's put retail here in the bottom,
[16:22] in the bottom, and maybe some technical things at the
[16:24] and maybe some technical things at the top.
[16:24] top. And immediately, I get some information
[16:27] And immediately, I get some information of how many square feet I have for the
[16:29] of how many square feet I have for the different programs.
[16:32] different programs. And this is just a great way of making
[16:34] And this is just a great way of making sure that you have your key figures in
[16:35] sure that you have your key figures in place all the time here for the project.
[16:38] place all the time here for the project. So, let's head into the top story and
[16:40] So, let's head into the top story and start generating things.
[16:43] start generating things. I simply select the whole story, click
[16:46] I simply select the whole story, click generate. I'm going to generate unit mix
[16:49] generate. I'm going to generate unit mix and corridors for this building.
[16:56] And straight away, here I launch it, I get some suggestions of core placement.
[17:00] get some suggestions of core placement. I've inputted some parameters here,
[17:03] I've inputted some parameters here, maximum egress distance, and so on. So,
[17:05] maximum egress distance, and so on. So, if I were to force my algorithm to
[17:08] if I were to force my algorithm to instead of adding these three
[17:10] instead of adding these three stairwells, just put one stairwell,
[17:13] stairwells, just put one stairwell, you will also see that I get some
[17:14] you will also see that I get some instant
[17:15] instant feedback that this is just simply too
[17:18] feedback that this is just simply too far away from the circulation. The the
[17:20] far away from the circulation. The the units we will generate over here will
[17:23] units we will generate over here will not be compliant according to the input
[17:26] not be compliant according to the input I've given it. So, let's jump back to
[17:29] I've given it. So, let's jump back to three.
[17:31] three. There we go.
[17:37] I'm happy with this one, and before I go ahead and generate the unit mix, I'm
[17:38] ahead and generate the unit mix, I'm just going to apply it here to my story.
[17:41] just going to apply it here to my story. There we go.
[17:42] There we go. And uh
[17:44] And uh everything you generate in Finch is also
[17:47] everything you generate in Finch is also editable. So, if I zoom in here, I can
[17:49] editable. So, if I zoom in here, I can simply say, "Okay, I would like my
[17:51] simply say, "Okay, I would like my circulation to be 24
[17:53] circulation to be 24 feet instead. I would like to align this
[17:57] feet instead. I would like to align this wall with this wall." Something like
[18:00] wall with this wall." Something like that.
[18:01] that. So, you can edit it to get it exactly
[18:04] So, you can edit it to get it exactly how you want.
[18:10] Then I simply select the areas where I would like to generate my new units, and
[18:12] would like to generate my new units, and I go and click generate unit mix around
[18:15] I go and click generate unit mix around existing corridor. Could be used in an
[18:18] existing corridor. Could be used in an existing project as well, turning an
[18:20] existing project as well, turning an office building into residential, and so
[18:22] office building into residential, and so on.
[18:23] on. Let's fire it up.
[18:25] Let's fire it up. Once again, it asks for some input. I
[18:28] Once again, it asks for some input. I just specify a unit mix, the input, and
[18:32] just specify a unit mix, the input, and so on. And you can see that the
[18:34] so on. And you can see that the algorithm start to work. And even if you
[18:37] algorithm start to work. And even if you have a complex shape like this, you can
[18:39] have a complex shape like this, you can see that the precision is actually very
[18:42] see that the precision is actually very high. I asked for
[18:44] high. I asked for 1250, I have 1250, I have 750, and so
[18:49] 1250, I have 1250, I have 750, and so on.
[18:51] on. And of course, there's always one or two
[18:54] And of course, there's always one or two apartments that take up the discrepancy
[18:56] apartments that take up the discrepancy here.
[19:02] But, for this particular design, I would like to have a little bit more control,
[19:04] like to have a little bit more control, and then I can add
[19:07] and then I can add I'm actually going to add some grid
[19:08] I'm actually going to add some grid lines here. There we go. And tell the
[19:11] lines here. There we go. And tell the algorithm to follow the grid lines. And
[19:14] algorithm to follow the grid lines. And what happens now is that the algorithm
[19:16] what happens now is that the algorithm try to find the optimal blend of
[19:20] try to find the optimal blend of snapping to the grid lines and still
[19:22] snapping to the grid lines and still maintaining the input that I've given
[19:25] maintaining the input that I've given it. Of course, this is a trade-off that
[19:27] it. Of course, this is a trade-off that you as an architect has to to
[19:29] you as an architect has to to decide where to go. Do you want exact
[19:32] decide where to go. Do you want exact sizes, or do you want it to to follow
[19:34] sizes, or do you want it to to follow the grid lines?
[19:39] But, I think I'm fairly happy with these results. Good enough. Let's
[19:42] results. Good enough. Let's put it in here.
[19:44] put it in here. And once again, if you have these kind
[19:46] And once again, if you have these kind of situations, where I asked for 1,000
[19:48] of situations, where I asked for 1,000 square feet, I got 1,000 square feet,
[19:51] square feet, I got 1,000 square feet, but me as an architect think it would be
[19:53] but me as an architect think it would be nice if this one aligns, then I can
[19:55] nice if this one aligns, then I can simply
[19:56] simply pull it hold down shift to lock it, and
[19:59] pull it hold down shift to lock it, and there you go.
[20:04] So, with the unit mix in place,
[20:07] with the unit mix in place, I'm very happy with this one. Uh before
[20:10] I'm very happy with this one. Uh before we go deeper and start generating floor
[20:13] we go deeper and start generating floor plans, I would like to show you my my
[20:15] plans, I would like to show you my my floor plan library. So, I simply head up
[20:18] floor plan library. So, I simply head up to the menu, I'm going to click on
[20:21] to the menu, I'm going to click on uh
[20:22] uh plans, I'm actually going to use another
[20:25] plans, I'm actually going to use another tab here.
[20:27] tab here. There you go.
[20:29] There you go. This is my floor plan library. I also
[20:33] This is my floor plan library. I also have access to my demo organization's
[20:36] have access to my demo organization's floor plans, and as I mentioned, this is
[20:38] floor plans, and as I mentioned, this is a great way of sharing design design uh
[20:41] a great way of sharing design design uh uh designs from previous projects, see
[20:44] uh designs from previous projects, see what your colleagues have been up to,
[20:45] what your colleagues have been up to, and so on. But I'm going to head into my
[20:47] and so on. But I'm going to head into my library, and I'm going to open one of my
[20:50] library, and I'm going to open one of my plans. Uh
[20:52] plans. Uh let's use this one.
[20:57] So, this is how a plan look. And what's special about the plans here
[21:00] And what's special about the plans here in Finch is that they are adaptive. So,
[21:03] in Finch is that they are adaptive. So, if I pull
[21:05] if I pull a wall, you can see that it stretches a
[21:08] a wall, you can see that it stretches a little bit.
[21:09] little bit. And that might not be how you would like
[21:12] And that might not be how you would like your architecture to behave, so then you
[21:14] your architecture to behave, so then you can also go in and set constraints. For
[21:16] can also go in and set constraints. For example, this is a bathroom module, or
[21:19] example, this is a bathroom module, or could be. Uh I simply lock the walls
[21:23] could be. Uh I simply lock the walls here, and then I have my uh corridors. I
[21:26] here, and then I have my uh corridors. I would like to say that they are allowed
[21:28] would like to say that they are allowed to be wider,
[21:30] to be wider, but not more narrow. And the next time I
[21:33] but not more narrow. And the next time I stretch my plan here, you can see that
[21:36] stretch my plan here, you can see that my bathroom stays the same, and the
[21:40] my bathroom stays the same, and the corridors becomes wider, and if I pull
[21:43] corridors becomes wider, and if I pull it together here, you can see that the
[21:45] it together here, you can see that the the small bathroom is getting squeezed,
[21:47] the small bathroom is getting squeezed, and not the corridors. So, this is just
[21:50] and not the corridors. So, this is just a great way of communicating with the
[21:51] a great way of communicating with the system how you would like your design to
[21:55] system how you would like your design to uh behave.
[21:57] uh behave. But uh let's jump back into the project.
[22:01] But uh let's jump back into the project. There you go.
[22:03] There you go. And let's start generating some floor
[22:06] And let's start generating some floor plans here. I'm going to select this
[22:08] plans here. I'm going to select this one, going to click generate floor plan,
[22:11] one, going to click generate floor plan, and then we give Finch a couple of
[22:13] and then we give Finch a couple of seconds to analyze where do we have the
[22:17] seconds to analyze where do we have the outside, where is the corridor, where's
[22:19] outside, where is the corridor, where's the neighboring apartment, and so on, to
[22:21] the neighboring apartment, and so on, to make sure we have a plan that is entered
[22:24] make sure we have a plan that is entered from the corridor and into the and have
[22:27] from the corridor and into the and have a bedrooms to to the facade and these
[22:29] a bedrooms to to the facade and these kind of things.
[22:34] And as we see results popping in here, they are being presented in three
[22:36] they are being presented in three categories. I have my own plans, they
[22:39] categories. I have my own plans, they come from my plan library.
[22:42] come from my plan library. Let's click one here.
[22:44] Let's click one here. I have
[22:45] I have plans from my colleagues that they have
[22:48] plans from my colleagues that they have designed that I can
[22:50] designed that I can browse around and see what they have
[22:52] browse around and see what they have been up to, and I have Finch generated
[22:55] been up to, and I have Finch generated results down here that I also can use as
[22:59] results down here that I also can use as inspiration and uh
[23:03] inspiration and uh apply here and then make it my own. But
[23:05] apply here and then make it my own. But uh since since uh my own plans fitted
[23:08] uh since since uh my own plans fitted very well here, I'm going to use one of
[23:11] very well here, I'm going to use one of them.
[23:18] And as you saw now, the colors changed when I baked it. Uh that is because I've
[23:20] when I baked it. Uh that is because I've changed the colors in this project. So,
[23:23] changed the colors in this project. So, because everything in Finch, both the
[23:25] because everything in Finch, both the design and and the look of things can be
[23:27] design and and the look of things can be customized to make it look exactly how
[23:31] customized to make it look exactly how you would like it in your practice.
[23:34] you would like it in your practice. And
[23:36] And when I have a plan in place, I'm just
[23:38] when I have a plan in place, I'm just going to go in here and click control C
[23:41] going to go in here and click control C to copy.
[23:42] to copy. I'm going to select some similar plans.
[23:46] I'm going to select some similar plans. Let's do it like this.
[23:49] Let's do it like this. And I'm going to click control V,
[23:52] And I'm going to click control V, and then the system uh
[23:54] and then the system uh rotates it as it understand, "No, you
[23:57] rotates it as it understand, "No, you need to enter from the corridor." And
[24:00] need to enter from the corridor." And you can see that it's uh copied out to
[24:02] you can see that it's uh copied out to these different units.
[24:04] these different units. As you see, I copied it also into a unit
[24:07] As you see, I copied it also into a unit that doesn't look exactly the same. I
[24:09] that doesn't look exactly the same. I have this undulating facade here. And
[24:12] have this undulating facade here. And then me as an architect can go in and
[24:14] then me as an architect can go in and say, "But I would like to use this plan
[24:16] say, "But I would like to use this plan anyhow. So, I would like to take stretch
[24:19] anyhow. So, I would like to take stretch these walls a little bit and say union."
[24:23] these walls a little bit and say union." And now
[24:24] And now the plan adapts to all of the different
[24:27] the plan adapts to all of the different units, and you can see the outline here
[24:29] units, and you can see the outline here of the different units where I used the
[24:31] of the different units where I used the plan. And they are still linked, even if
[24:33] plan. And they are still linked, even if they are a little bit different. So, if
[24:35] they are a little bit different. So, if I were to move my little Eames chair
[24:38] I were to move my little Eames chair here, of course, it updates in all of
[24:41] here, of course, it updates in all of the units. And this is a this is a great
[24:44] the units. And this is a this is a great way of of working with repetition in
[24:47] way of of working with repetition in your design, even if it's not exactly
[24:50] your design, even if it's not exactly the same uh apartments.
[24:59] And uh then I work my way through the project, and I can show you how it looks
[25:02] project, and I can show you how it looks when we have a lot of plans. This is a
[25:05] when we have a lot of plans. This is a full project. Uh
[25:08] full project. Uh and the last thing I would like to show
[25:10] and the last thing I would like to show you before we heading in to uh Revit the
[25:14] you before we heading in to uh Revit the Revit demo is, of course, Archie, our
[25:17] Revit demo is, of course, Archie, our design assistant I mentioned earlier on
[25:19] design assistant I mentioned earlier on here.
[25:21] here. I'm going to open him him here, and then
[25:23] I'm going to open him him here, and then I can
[25:25] I can do things like let's do the same uh
[25:27] do things like let's do the same uh similar example.
[25:29] similar example. Uh
[25:37] Make sure all my pocket doors are 2 inches from the wall.
[25:42] 2 inches from the wall. Let's see what happens.
[25:50] And then we give Archie a couple of seconds to think about it. Uh let's see.
[25:55] seconds to think about it. Uh let's see. From nearest wall, that
[25:57] From nearest wall, that sounds about right.
[26:00] sounds about right. So, now it goes into the different plans
[26:02] So, now it goes into the different plans here, and this is the pocket doors, of
[26:04] here, and this is the pocket doors, of course. And yeah, you can see he moved
[26:07] course. And yeah, you can see he moved that one, and then he's just working his
[26:09] that one, and then he's just working his way through all of my units here in the
[26:12] way through all of my units here in the project. And this is a great way of
[26:16] project. And this is a great way of making sure everything is ready for
[26:18] making sure everything is ready for going out to uh full BIM model in Revit
[26:22] going out to uh full BIM model in Revit later. And there is just something
[26:24] later. And there is just something pleasing about, you know, starting
[26:27] pleasing about, you know, starting Archie and see how he navigates around
[26:30] Archie and see how he navigates around in the project while I'll have a coffee
[26:33] in the project while I'll have a coffee or think about the bigger questions here
[26:35] or think about the bigger questions here in the project.
[26:42] Okay. Uh while he's doing that, I'm just going to show you super quickly how this
[26:44] going to show you super quickly how this project would look in Revit later. So,
[26:49] project would look in Revit later. So, just to
[26:50] just to not
[26:51] not let you wait while Revit build the
[26:53] let you wait while Revit build the models, it takes it takes a couple of
[26:55] models, it takes it takes a couple of minutes for Revit to build a model. So,
[26:57] minutes for Revit to build a model. So, I did it before this demo. This is how
[27:00] I did it before this demo. This is how it looks in Revit when it comes in. It
[27:04] it looks in Revit when it comes in. It is native Revit geometry, as mentioned,
[27:08] is native Revit geometry, as mentioned, Revit walls, Revit doors, Revit
[27:10] Revit walls, Revit doors, Revit families.
[27:11] families. And
[27:12] And uh
[27:13] uh yeah, this is it for the demo part.
[27:17] yeah, this is it for the demo part. Now, Amelia will show you how it works
[27:20] Now, Amelia will show you how it works when you import a project to Revit, and
[27:24] when you import a project to Revit, and I think she also will uh mention that we
[27:27] I think she also will uh mention that we also support the same kind of uh things
[27:29] also support the same kind of uh things in Archicad.
[27:31] in Archicad. I think that's it. Did I forget about
[27:33] I think that's it. Did I forget about anything, Amelia or Pamela?
[27:41] I think that was great. Thanks, Jesper. Uh I'll go ahead and share my screen
[27:43] Uh I'll go ahead and share my screen here, and uh yeah, as Jesper mentioned,
[27:44] here, and uh yeah, as Jesper mentioned, we'll go through the
[27:47] we'll go through the uh
[27:48] uh Just going to move here.
[27:51] Just going to move here. Uh
[27:52] Uh we will be going through the uh workflow
[27:54] we will be going through the uh workflow for both Revit as well as Archicad. Uh
[27:58] for both Revit as well as Archicad. Uh so, here we are inside of Finch. Uh this
[28:00] so, here we are inside of Finch. Uh this is a high-rise tower located in New
[28:02] is a high-rise tower located in New York, and just to give a quick idea of
[28:04] York, and just to give a quick idea of kind of how Finch can be used as a
[28:05] kind of how Finch can be used as a presentation tool as well. When we're at
[28:06] presentation tool as well. When we're at the stage of where we're ready to bring
[28:08] the stage of where we're ready to bring this down into Revit, uh we of course
[28:10] this down into Revit, uh we of course always have our programs on the left
[28:11] always have our programs on the left side or on the right side here. So, we
[28:13] side or on the right side here. So, we have, you know, residential GFA, GIA,
[28:15] have, you know, residential GFA, GIA, etc. Uh we can even set up, you know,
[28:17] etc. Uh we can even set up, you know, custom calculations for carbon revenue,
[28:19] custom calculations for carbon revenue, these sort of things. So, a lot of the
[28:21] these sort of things. So, a lot of the stuff that you also will do when you go
[28:22] stuff that you also will do when you go down into Revit, you can actually have
[28:24] down into Revit, you can actually have up here in Finch as well. Looking at
[28:26] up here in Finch as well. Looking at space types, vertical stacking, unit
[28:28] space types, vertical stacking, unit mix, as well as some schedules of
[28:30] mix, as well as some schedules of objects, doors, walls, these sort of
[28:31] objects, doors, walls, these sort of things.
[28:32] things. But uh once we're ready to go down into
[28:34] But uh once we're ready to go down into Revit, we'll just go ahead and open that
[28:35] Revit, we'll just go ahead and open that up. Here we can see this uh full
[28:37] up. Here we can see this uh full building modeled in 3D. Uh and as you
[28:39] building modeled in 3D. Uh and as you saw in the the KPF video, we can have
[28:41] saw in the the KPF video, we can have both 2D and 3D furniture. In this
[28:44] both 2D and 3D furniture. In this particular model, we're working
[28:45] particular model, we're working primarily with 2D furniture. Uh and you
[28:47] primarily with 2D furniture. Uh and you can also, of course, map whatever you're
[28:49] can also, of course, map whatever you're bringing in here. Uh if we just go ahead
[28:51] bringing in here. Uh if we just go ahead and take a look in 2D, we can see that
[28:54] and take a look in 2D, we can see that we have, you know, those area plans for
[28:56] we have, you know, those area plans for GFA, NIA, these sort of things. And we
[28:59] GFA, NIA, these sort of things. And we of course also are working with those
[29:01] of course also are working with those model groups. So, the model groups we
[29:02] model groups. So, the model groups we have up in Finch with our plans, all of
[29:05] have up in Finch with our plans, all of these type A, type B, studio, this is
[29:08] these type A, type B, studio, this is brought all the way down into Revit, and
[29:09] brought all the way down into Revit, and these names, of course, are retained. Uh
[29:12] these names, of course, are retained. Uh and as Jesper mentioned, we had to have
[29:14] and as Jesper mentioned, we had to have the custom mapping. So, in this
[29:15] the custom mapping. So, in this particular file, everything is getting
[29:17] particular file, everything is getting mapped as Finch basic walls. Uh but when
[29:20] mapped as Finch basic walls. Uh but when you are importing things, you can switch
[29:21] you are importing things, you can switch them to your own templates um as as
[29:23] them to your own templates um as as default.
[29:25] default. If we want to go ahead and generate
[29:27] If we want to go ahead and generate inside of Revit, we can also do that.
[29:29] inside of Revit, we can also do that. So, we often say that you know, if
[29:31] So, we often say that you know, if you're kind of later stage in the
[29:32] you're kind of later stage in the project, or maybe you're just using
[29:34] project, or maybe you're just using Finch for the very first time, this can
[29:35] Finch for the very first time, this can be a really nice way to uh get up and
[29:38] be a really nice way to uh get up and running with Finch. Essentially, we just
[29:40] running with Finch. Essentially, we just want to click inside of the unit we want
[29:41] want to click inside of the unit we want to generate in, click on the entrance
[29:43] to generate in, click on the entrance door wall, and then hit finish, and then
[29:45] door wall, and then hit finish, and then instantly we're going to be leveraging
[29:47] instantly we're going to be leveraging that data set that we have up in Finch
[29:50] that data set that we have up in Finch down here in the Revit environment that
[29:51] down here in the Revit environment that we're very familiar with.
[29:53] we're very familiar with. So we'll see these start to pop up. And
[29:55] So we'll see these start to pop up. And as always you have a few different
[29:56] as always you have a few different result sets. So my own plans, my firm's
[29:58] result sets. So my own plans, my firm's plans, Finch plans, you have a lot to
[30:00] plans, Finch plans, you have a lot to choose from. And you can just click
[30:01] choose from. And you can just click those down to bring them into the Revit
[30:03] those down to bring them into the Revit environment.
[30:05] environment. If we jump over into Archicad, same
[30:07] If we jump over into Archicad, same thing goes there.
[30:09] thing goes there. Archicad up. So here a very similar
[30:11] Archicad up. So here a very similar environment. We of course have that 3D
[30:13] environment. We of course have that 3D model brought down here. Take a look
[30:15] model brought down here. Take a look there.
[30:16] there. And everything's coming in as expected.
[30:17] And everything's coming in as expected. You can custom map this here as well.
[30:20] You can custom map this here as well. And same goes if we want to go ahead and
[30:22] And same goes if we want to go ahead and generate a plan. We can go ahead and
[30:23] generate a plan. We can go ahead and click generate in this zone.
[30:25] click generate in this zone. And then the interface you'll notice is
[30:27] And then the interface you'll notice is actually a little bit different here. So
[30:28] actually a little bit different here. So we are going to kind of work in more of
[30:30] we are going to kind of work in more of that Finch environment that you're
[30:31] that Finch environment that you're familiar with. So we can go ahead and
[30:33] familiar with. So we can go ahead and say that we want to know the entrance
[30:35] say that we want to know the entrance here.
[30:36] here. Go ahead and generate. And then I'm just
[30:37] Go ahead and generate. And then I'm just going to drag this over so you can see
[30:39] going to drag this over so you can see the whole window here.
[30:42] the whole window here. Like so.
[30:43] Like so. And then we have all of our filters. We
[30:45] And then we have all of our filters. We can check for compliant plans, search by
[30:48] can check for compliant plans, search by region tags, all of that here. You know,
[30:50] region tags, all of that here. You know, preview the plans as we are used to. And
[30:53] preview the plans as we are used to. And if I want to actually work with this
[30:54] if I want to actually work with this plan, I can just assign it out. And we
[30:56] plan, I can just assign it out. And we are working with hot links as well. So
[30:57] are working with hot links as well. So same as those model groups will pop down
[30:59] same as those model groups will pop down here into Archicad.
[31:02] here into Archicad. All right. And then we have that there.
[31:04] All right. And then we have that there. So I'll just move this back over. We can
[31:05] So I'll just move this back over. We can take a look at what we received. So
[31:07] take a look at what we received. So looks pretty similar to what we've
[31:08] looks pretty similar to what we've already downloaded. Everything's coming
[31:09] already downloaded. Everything's coming down in our our own templates there.
[31:12] down in our our own templates there. All right. That's what I have for for
[31:15] All right. That's what I have for for Archicad and Revit. So I'll hand it back
[31:17] Archicad and Revit. So I'll hand it back over to to Jesper and Pamela.
[31:25] Thank you, Amelia. Shall we jump into Q&amp;A?
[31:30] Let's see. The first question is around when the
[31:31] The first question is around when the education solutions will be available.
[31:34] education solutions will be available. We have started to do a couple of
[31:36] We have started to do a couple of collaborations with a few universities.
[31:38] collaborations with a few universities. This is a resource question. But
[31:41] This is a resource question. But hopefully we can launch more broadly to
[31:43] hopefully we can launch more broadly to students over here later this year or
[31:46] students over here later this year or the next year.
[31:48] the next year. Unfortunately not ETA on that yet
[31:50] Unfortunately not ETA on that yet though.
[31:51] though. The second question is what are the
[31:54] The second question is what are the links between Archicad and Finch? And
[31:55] links between Archicad and Finch? And this is what Amelia just showed. Feel
[31:57] this is what Amelia just showed. Feel free to ask uh
[31:59] free to ask uh uh
[32:00] uh more detailed question if you if you
[32:02] more detailed question if you if you have
[32:03] have more specific question around Archicad.
[32:09] And the next question is if Finch automatically split the building into
[32:11] automatically split the building into stories or was the facade built split
[32:14] stories or was the facade built split already? Do you Would you like to take
[32:16] already? Do you Would you like to take this one, Jesper?
[32:21] Yes. So uh we automatically split the mesh into
[32:23] we automatically split the mesh into stories. But of course you can set your
[32:25] stories. But of course you can set your own story height. And you also can
[32:28] own story height. And you also can upload your storage if you are an
[32:30] upload your storage if you are an advanced Grasshopper user and so on. So
[32:33] advanced Grasshopper user and so on. So you have total freedom over your
[32:35] you have total freedom over your stories.
[32:41] Uh next person here sounds like you have a bug with the Archicad integration.
[32:43] a bug with the Archicad integration. Feel free to send this into our chat. If
[32:46] Feel free to send this into our chat. If you are Mac user, want to let you know
[32:48] you are Mac user, want to let you know that
[32:49] that we currently do not support that yet.
[32:51] we currently do not support that yet. We're waiting for approval from from
[32:53] We're waiting for approval from from Apple. But if you're facing any any
[32:55] Apple. But if you're facing any any issues, just write to us in the chat and
[32:58] issues, just write to us in the chat and we will forward this to our development
[32:59] we will forward this to our development team.
[33:03] Uh the next question is if it's possible to add back of house program within
[33:05] to add back of house program within residential floor plans. I'm not
[33:07] residential floor plans. I'm not familiar with back of house programs.
[33:10] familiar with back of house programs. Anyone else here? Amelia, Jesper?
[33:16] Uh if I understand if it's just about the types of um
[33:18] the types of um rooms that you can have inside of your
[33:20] rooms that you can have inside of your your plan. I mean this is completely
[33:21] your plan. I mean this is completely custom. So anything that goes into the
[33:23] custom. So anything that goes into the data set, um room typologies, spatial
[33:26] data set, um room typologies, spatial layouts, hierarchies, this is all
[33:28] layouts, hierarchies, this is all reflected in the results that that you
[33:29] reflected in the results that that you get.
[33:31] get. Yeah.
[33:32] Yeah. Good.
[33:33] Good. Uh the next question if it if it's
[33:35] Uh the next question if it if it's possible to add bedroom closets
[33:37] possible to add bedroom closets automatically in each bedroom. This is a
[33:39] automatically in each bedroom. This is a type of data that we can embed to the
[33:42] type of data that we can embed to the pro plan library that Jesper just
[33:44] pro plan library that Jesper just showed. Uh here we can add closets and
[33:47] showed. Uh here we can add closets and so on. And that will
[33:50] so on. And that will be included when you generate from your
[33:52] be included when you generate from your own library.
[33:58] The next one is about uh construction for construction purposes.
[34:00] construction for construction purposes. How can you construct the amount of unit
[34:02] How can you construct the amount of unit types? In my practice unit types aren't
[34:04] types? In my practice unit types aren't just same area but the same footprint as
[34:06] just same area but the same footprint as well.
[34:08] well. Jesper, would you like to take this one?
[34:10] Jesper, would you like to take this one? I didn't hear the the whole question.
[34:12] I didn't hear the the whole question. Sorry.
[34:14] Sorry. Sorry. Let's see. So how can you
[34:16] Sorry. Let's see. So how can you construct the amount of unit types?
[34:23] For repetition. Yes, so that happens when when you
[34:25] Yes, so that happens when when you generate the unit mix. Of course, in my
[34:29] generate the unit mix. Of course, in my case I had an undulating facade.
[34:30] case I had an undulating facade. Everyone will become unique. But in the
[34:34] Everyone will become unique. But in the KPF workshop where we had a straight
[34:36] KPF workshop where we had a straight building, I mean
[34:38] building, I mean since the the program tries to find
[34:41] since the the program tries to find exact area, they will end up the
[34:45] exact area, they will end up the same shape and and the size. So that
[34:49] same shape and and the size. So that happens by by default. Of course you
[34:51] happens by by default. Of course you will always get some unique ones in
[34:53] will always get some unique ones in corners and and this kind of things just
[34:55] corners and and this kind of things just as you would when you design it
[34:56] as you would when you design it yourself.
[35:01] Yes. Um Sandra is writing, this is really
[35:03] Um Sandra is writing, this is really exciting, guys. Well done. Thank you. Is
[35:06] exciting, guys. Well done. Thank you. Is it possible to set up criteria for how
[35:08] it possible to set up criteria for how GLA, GFA, etc. is measured?
[35:15] Uh at the moment we support the standard ones, gross floor area, net internal
[35:17] ones, gross floor area, net internal area, gross internal area. We will
[35:20] area, gross internal area. We will here later this year uh launch custom
[35:25] here later this year uh launch custom ways to calculate these kind of
[35:27] ways to calculate these kind of different things where you as a user
[35:29] different things where you as a user will be able to set should we measure
[35:31] will be able to set should we measure from the center of the wall or from the
[35:33] from the center of the wall or from the inside or outside and this kind of
[35:35] inside or outside and this kind of things. Right now we support the the
[35:37] things. Right now we support the the most common ones. But more custom is is
[35:41] most common ones. But more custom is is coming here during the year.
[35:43] coming here during the year. Yep.
[35:45] Yep. Next one is for Amelia. Uh when
[35:46] Next one is for Amelia. Uh when exporting to Revit, where do do the
[35:49] exporting to Revit, where do do the family come from? I doors, windows, etc.
[35:52] family come from? I doors, windows, etc. Are these standard Autodesk families or
[35:54] Are these standard Autodesk families or can you use practice specific ones?
[35:57] can you use practice specific ones? Yes, so when you export you have a a
[36:00] Yes, so when you export you have a a dialogue box. And then you can actually
[36:02] dialogue box. And then you can actually auto map them. So you can select all of
[36:04] auto map them. So you can select all of the the walls that are in your Finch
[36:05] the the walls that are in your Finch project and auto map them. And then you
[36:07] project and auto map them. And then you can actually save these settings as
[36:08] can actually save these settings as well. So you only need to set this up
[36:09] well. So you only need to set this up once. But if you don't do this, they
[36:11] once. But if you don't do this, they just come in as those Finch generic
[36:13] just come in as those Finch generic ones. But yeah, you can have them custom
[36:15] ones. But yeah, you can have them custom mapped to anything whether it's doors,
[36:17] mapped to anything whether it's doors, slabs, furniture, walls, all of that.
[36:20] slabs, furniture, walls, all of that. And actually if you do upload your
[36:21] And actually if you do upload your furniture from Revit to begin with, then
[36:23] furniture from Revit to begin with, then it will automatically do that as well.
[36:28] Yes. The next question is if this works with
[36:31] The next question is if this works with UK standards as well.
[36:32] UK standards as well. Yes. We have many UK firms using Finch.
[36:37] Yes. We have many UK firms using Finch. Few of them you might see here behind
[36:38] Few of them you might see here behind me.
[36:40] me. &gt;&gt; [clears throat]
[36:40] &gt;&gt; [clears throat] &gt;&gt; Uh and we can embed
[36:42] &gt;&gt; Uh and we can embed uh a lot of different type of
[36:44] uh a lot of different type of regulations both into the plan library
[36:46] regulations both into the plan library but also the input that you can give the
[36:49] but also the input that you can give the the optimized unit mix algorithm and so
[36:51] the optimized unit mix algorithm and so on. Feel free to reach out to us
[36:53] on. Feel free to reach out to us afterwards if you have a specific
[36:55] afterwards if you have a specific project that you're considering using
[36:57] project that you're considering using Finch. Happy to help you out.
[37:04] The next one is also about regulations,
[37:06] also about regulations, building and technical in various
[37:08] building and technical in various countries.
[37:09] countries. Uh for that I want to say that we have
[37:10] Uh for that I want to say that we have customers in more than 20 countries. We
[37:13] customers in more than 20 countries. We have customers in US, in Europe, in the
[37:14] have customers in US, in Europe, in the Middle East, Asia, and Australia.
[37:17] Middle East, Asia, and Australia. Um so we are quite familiar to working
[37:19] Um so we are quite familiar to working with very different type of regulations.
[37:21] with very different type of regulations. And with this is why we help all of our
[37:23] And with this is why we help all of our customers to build up this plan library
[37:25] customers to build up this plan library to make sure that this is where you can
[37:27] to make sure that this is where you can embed the type of regulations that you
[37:29] embed the type of regulations that you need to adhere to in that level of
[37:30] need to adhere to in that level of detail. And then in the
[37:33] detail. And then in the order algorithms, this is where you can
[37:36] order algorithms, this is where you can again steer and interact with everything
[37:38] again steer and interact with everything that is being generated.
[37:41] that is being generated. And I usually say that Finch can
[37:44] And I usually say that Finch can probably adhere to depending on where
[37:46] probably adhere to depending on where you are, what part of the world you are,
[37:48] you are, what part of the world you are, to 50 to 70% of the rules.
[37:51] to 50 to 70% of the rules. But you are as an architect are always
[37:53] But you are as an architect are always in charge. You need to evaluate the
[37:55] in charge. You need to evaluate the result and make sure it is 100%
[37:59] result and make sure it is 100% compliant and take it from those 50 to
[38:01] compliant and take it from those 50 to 100%.
[38:08] The next question is if it read
[38:09] read and convert any units.
[38:12] and convert any units. Like millimeter, meters. I'm not sure I
[38:14] Like millimeter, meters. I'm not sure I understand the question. Anyone else?
[38:17] understand the question. Anyone else? Uh if I understand, you can upload
[38:19] Uh if I understand, you can upload straight from Rhino Revit in any
[38:23] straight from Rhino Revit in any units. And you can also switch between
[38:25] units. And you can also switch between imperial and metric inside of Finch.
[38:28] imperial and metric inside of Finch. Yep.
[38:34] This one is also for you, Amelia. Once you export to Revit, can you go
[38:35] Once you export to Revit, can you go back to Finch for redesign?
[38:37] back to Finch for redesign? Thank you. Great webinar. Thank you for
[38:39] Thank you. Great webinar. Thank you for attending the aux.
[38:44] Uh so once you export to Finch, you are kind of doing this conversion to to BIM.
[38:46] kind of doing this conversion to to BIM. So it doesn't kind of flow both ways.
[38:49] So it doesn't kind of flow both ways. But if you have really big changes, we
[38:51] But if you have really big changes, we advise you to kind of go back into
[38:52] advise you to kind of go back into Finch, redesign, regenerate, work with
[38:54] Finch, redesign, regenerate, work with it there. If you do have minor changes,
[38:56] it there. If you do have minor changes, you know, just a wall here and there,
[38:57] you know, just a wall here and there, then what I showed generating inside of
[39:00] then what I showed generating inside of Revit can be a really good option. So I
[39:01] Revit can be a really good option. So I would say it just depends on the the
[39:03] would say it just depends on the the scale of the changes. But we kind of
[39:05] scale of the changes. But we kind of advise our customers to stay inside of
[39:08] advise our customers to stay inside of Finch for as long as possible, iterate
[39:09] Finch for as long as possible, iterate there. Because once you do go out to
[39:11] there. Because once you do go out to Revit, you are kind of doing that export
[39:13] Revit, you are kind of doing that export that is a little bit, you know, harder
[39:15] that is a little bit, you know, harder than staying in Finch where you can be
[39:16] than staying in Finch where you can be really flexible and iterate quickly.
[39:22] Good. Uh Anna here wrote a follow-up question.
[39:24] Uh Anna here wrote a follow-up question. I think I misunderstood the first one.
[39:26] I think I misunderstood the first one. The question was about educational
[39:27] The question was about educational solution. Uh it's about the educational
[39:30] solution. Uh it's about the educational architecture as residential, commercial,
[39:32] architecture as residential, commercial, and so on. Will there be a solution for
[39:34] and so on. Will there be a solution for those kind of buildings as well? And
[39:36] those kind of buildings as well? And when?
[39:37] when? We are actually already supporting
[39:39] We are actually already supporting educational projects through the Nano
[39:41] educational projects through the Nano Banana extension.
[39:43] Banana extension. I don't know where Yesper do you have
[39:44] I don't know where Yesper do you have something to demo? Maybe not educational
[39:46] something to demo? Maybe not educational uh but we have offices as an example
[39:48] uh but we have offices as an example just to show how the Nana Banana
[39:51] just to show how the Nana Banana uh interface works in Finch.
[39:53] uh interface works in Finch. Yeah, yeah, sure.
[39:55] Yeah, yeah, sure. Let's
[39:57] Let's So, this was the project we were
[39:59] So, this was the project we were working in.
[40:01] working in. Uh let's just add a wall here and
[40:03] Uh let's just add a wall here and generate an office instead. So,
[40:06] generate an office instead. So, I'm just going to delete this part of
[40:08] I'm just going to delete this part of the building.
[40:09] the building. Uh and then I'm going to say select it
[40:12] Uh and then I'm going to say select it and going to generate with Nana Banana
[40:15] and going to generate with Nana Banana and I can just office for 40 people uh
[40:19] and I can just office for 40 people uh and give it
[40:20] and give it and uh
[40:21] and uh of course, you can develop this prompts
[40:24] of course, you can develop this prompts a lot and be very intricate and complex.
[40:27] a lot and be very intricate and complex. Now, generate an office for the people.
[40:30] Now, generate an office for the people. We will see how the the results becomes
[40:32] We will see how the the results becomes here.
[40:33] here. Uh I would say the main benefit with
[40:35] Uh I would say the main benefit with using Nana Banana in Finch compared to
[40:39] using Nana Banana in Finch compared to just running it in in Google as as you
[40:42] just running it in in Google as as you know, it's of course that we
[40:45] know, it's of course that we curate the input and output. So, we send
[40:48] curate the input and output. So, we send the geometry, the the unit where you
[40:51] the geometry, the the unit where you want to generate into Nana Banana. Here
[40:54] want to generate into Nana Banana. Here we're getting some results.
[40:56] we're getting some results. Uh here is an office
[40:58] Uh here is an office and we can see some different results
[41:02] and we can see some different results here.
[41:03] here. And let's let's take one. I think I like
[41:06] And let's let's take one. I think I like this one the best. Let's choose this
[41:08] this one the best. Let's choose this one.
[41:09] one. So, of course, we provide that and then
[41:12] So, of course, we provide that and then we also if we click find walls here,
[41:16] we also if we click find walls here, Finch also converts the yeah, already
[41:19] Finch also converts the yeah, already now uh
[41:21] now uh the let's see turn on this one. Uh the
[41:25] the let's see turn on this one. Uh the image into editable geometry. Right now,
[41:29] image into editable geometry. Right now, it's walls like this and of course, you
[41:32] it's walls like this and of course, you can see that we can get in and edit
[41:34] can see that we can get in and edit these kind of things manually. You can
[41:36] these kind of things manually. You can take the doors and change them and work
[41:40] take the doors and change them and work with them. The next uh furnitures is
[41:43] with them. The next uh furnitures is coming as well.
[41:46] coming as well. And uh of course, now I typed the office
[41:48] And uh of course, now I typed the office you could
[41:49] you could since it's Google anything that's on the
[41:51] since it's Google anything that's on the internet you can generate here if it's
[41:53] internet you can generate here if it's educational or
[41:55] educational or mechanical space and so on.
[42:04] Good. Thank you. Uh the next question is from David. Uh a
[42:07] Uh the next question is from David. Uh a link maintained between Finch and Revit
[42:09] link maintained between Finch and Revit ArchiCAD for when individual rooms are
[42:11] ArchiCAD for when individual rooms are updated in Finch or is it one-way
[42:13] updated in Finch or is it one-way traffic?
[42:15] traffic? I think you already covered this,
[42:16] I think you already covered this, Amelia.
[42:23] Uh the next question is what about various technical systems and their
[42:24] various technical systems and their integrations in the building, technical
[42:26] integrations in the building, technical shafts, spaces for the
[42:29] shafts, spaces for the tech and so on.
[42:31] tech and so on. Uh maybe I can answer this one. Uh
[42:34] Uh maybe I can answer this one. Uh it depends on the project. It depends on
[42:35] it depends on the project. It depends on how far you come with the project. We
[42:37] how far you come with the project. We can of course incorporate as an example
[42:39] can of course incorporate as an example grid lines. For some customers we
[42:41] grid lines. For some customers we include shafts already in their plans or
[42:44] include shafts already in their plans or if they prefer to to add this later. Uh
[42:47] if they prefer to to add this later. Uh it's very case by case.
[43:05] Uh the next question is issue of the details. How is it solved as well as
[43:07] details. How is it solved as well as thickness of elements?
[43:13] So, thickness Yeah, thickness of elements and walls and so on is embedded
[43:16] elements and walls and so on is embedded in your floor plan library. So, if you
[43:18] in your floor plan library. So, if you set that you want the
[43:20] set that you want the 4 in or 120 mm in a wall, the result you
[43:24] 4 in or 120 mm in a wall, the result you generate will also have these
[43:26] generate will also have these dimension. And there was one more part
[43:29] dimension. And there was one more part of the question, right, Pamela?
[43:36] How is it solved as well as yeah. Yeah.
[43:37] Yeah. Yeah, I think I can kind of answered
[43:39] Yeah, I think I can kind of answered that one a bit.
[43:42] that one a bit. Good. Uh there's a follow-up regarding
[43:45] Good. Uh there's a follow-up regarding ArchiCAD.
[43:46] ArchiCAD. Uh if your unit type size in the same
[43:49] Uh if your unit type size in the same in the same type IA, would this be
[43:52] in the same type IA, would this be coming into ArchiCAD as a moody or
[43:54] coming into ArchiCAD as a moody or module type?
[43:56] module type? Uh when we're bringing in the the model
[43:58] Uh when we're bringing in the the model groups, they're coming in as hotlinks.
[43:59] groups, they're coming in as hotlinks. So, they're linked similar to how
[44:01] So, they're linked similar to how they're coming in as model groups into
[44:03] they're coming in as model groups into Revit. Uh
[44:05] Revit. Uh but all of you can actually test the
[44:06] but all of you can actually test the ArchiCAD plugin even on the the free
[44:08] ArchiCAD plugin even on the the free tier. So, if you guys want to go in and
[44:10] tier. So, if you guys want to go in and kind of see the geometry that you get
[44:11] kind of see the geometry that you get out, you can download one of the sample
[44:12] out, you can download one of the sample projects and have a look and kind of
[44:14] projects and have a look and kind of inspect the geometry.
[44:21] Yes. Uh the next question is about roadmap.
[44:23] Uh the next question is about roadmap. What are your future plans for software
[44:25] What are your future plans for software and what features do you hope to add in
[44:26] and what features do you hope to add in the future?
[44:27] the future? Great seminar. Thanks. Thank you for
[44:30] Great seminar. Thanks. Thank you for attending. Yesper, would you like to
[44:31] attending. Yesper, would you like to answer this one?
[44:34] answer this one? Yeah, of course. So,
[44:36] Yeah, of course. So, the main things as I showed in the
[44:37] the main things as I showed in the slides here of is of course more
[44:41] slides here of is of course more typologies and the 3D editor and what
[44:44] typologies and the 3D editor and what and and and right now we sits in between
[44:49] and and and right now we sits in between if we say Rhino SketchUp these kind of
[44:50] if we say Rhino SketchUp these kind of design software and then we have the BIM
[44:53] design software and then we have the BIM software where we have ArchiCAD and
[44:54] software where we have ArchiCAD and Revit and and we generate and work with
[44:57] Revit and and we generate and work with the inside of the building.
[45:00] the inside of the building. Uh we would like to go further into the
[45:02] Uh we would like to go further into the early stages as well so you can start
[45:04] early stages as well so you can start with the massing in Finch. That's why
[45:05] with the massing in Finch. That's why we're building the 3D editor. And we're
[45:07] we're building the 3D editor. And we're also going in the other direction adding
[45:10] also going in the other direction adding uh
[45:11] uh uh documentation capabilities within
[45:13] uh documentation capabilities within Finch so we prolong the
[45:17] Finch so we prolong the the time spent in Finch before you
[45:20] the time spent in Finch before you need to jump into your more rigid BIM
[45:23] need to jump into your more rigid BIM software that probably is very good at
[45:26] software that probably is very good at documentation but maybe not as flexible
[45:29] documentation but maybe not as flexible when it comes to the design phase.
[45:33] when it comes to the design phase. Good. Thank you.
[45:35] Good. Thank you. Uh this fits quite well into the next
[45:37] Uh this fits quite well into the next question which is about how does Finch
[45:39] question which is about how does Finch understand the unit shape being
[45:41] understand the unit shape being rectangular, square or with curves,
[45:42] rectangular, square or with curves, etc.? Do we need to model them in Revit
[45:44] etc.? Do we need to model them in Revit first and import it into Finch and then
[45:46] first and import it into Finch and then import to Revit again or do we draw in
[45:48] import to Revit again or do we draw in Finch directly first?
[45:50] Finch directly first? Uh so, right now you have to upload your
[45:53] Uh so, right now you have to upload your mass from Revit, Rhino, Grasshopper or
[45:56] mass from Revit, Rhino, Grasshopper or Autodesk Forma. You design inside in
[45:58] Autodesk Forma. You design inside in Finch and then you can bring this back
[46:00] Finch and then you can bring this back to your preferred software as proper BIM
[46:02] to your preferred software as proper BIM geometry. And just as Yesper mentioned,
[46:04] geometry. And just as Yesper mentioned, we're building up our own 3D editor
[46:06] we're building up our own 3D editor which would allow you to start in Finch
[46:09] which would allow you to start in Finch quite soon.
[46:15] Good. The next question is after we modify the
[46:17] The next question is after we modify the project in ArchiCAD Revit, can we import
[46:19] project in ArchiCAD Revit, can we import the modification back to Finch? Sort of
[46:21] the modification back to Finch? Sort of the inverse process. I think we already
[46:24] the inverse process. I think we already covered it, right?
[46:26] covered it, right? The next question is if we support the
[46:28] The next question is if we support the direct integration with Autodesk Forma.
[46:30] direct integration with Autodesk Forma. Yes, we do. We have a built-in extension
[46:32] Yes, we do. We have a built-in extension for Autodesk Forma so you can
[46:35] for Autodesk Forma so you can fetch context,
[46:37] fetch context, surrounding buildings and so on, develop
[46:39] surrounding buildings and so on, develop your mass in Forma, bring this into
[46:41] your mass in Forma, bring this into Finch and then uh export it to Revit.
[46:44] Finch and then uh export it to Revit. That is a very popular workflow. We
[46:45] That is a very popular workflow. We presented this at Autodesk University
[46:47] presented this at Autodesk University last year. Uh there's a YouTube clip
[46:50] last year. Uh there's a YouTube clip on exactly what this workflow looks
[46:52] on exactly what this workflow looks like. It's a very popular workflow
[46:55] like. It's a very popular workflow amongst our our customers, actually.
[47:01] The next question is if there is an option for creating renderings for the
[47:03] option for creating renderings for the spaces.
[47:04] spaces. Uh is it something Archi does or is it
[47:07] Uh is it something Archi does or is it only in our development environment?
[47:09] only in our development environment? Uh well, you can't tell Archi to create
[47:13] Uh well, you can't tell Archi to create render and it you will get something out
[47:15] render and it you will get something out but no, it's not something we do. We we
[47:17] but no, it's not something we do. We we work with space planning and and and so
[47:20] work with space planning and and and so on and I think there's other tools that
[47:23] on and I think there's other tools that built specifically for this out there
[47:25] built specifically for this out there that you should uh
[47:27] that you should uh uh play around with.
[47:40] Next question if it's possible to create curtain walls,
[47:42] curtain walls, modulations through the facade layout.
[47:50] Uh not at the moment. We work at the inside of the building. We have just
[47:52] inside of the building. We have just launched the ability to add
[47:55] launched the ability to add windows. Of course, you can add a lot of
[47:57] windows. Of course, you can add a lot of windows turning it into a curtain uh
[48:00] windows turning it into a curtain uh curtain wall but no, not at the moment.
[48:03] curtain wall but no, not at the moment. We still focus very much on on the
[48:05] We still focus very much on on the inside.
[48:12] We have a next question from Rodrigo. He asked if it supports Chilean norms. As
[48:14] asked if it supports Chilean norms. As mentioned before, we have customers from
[48:16] mentioned before, we have customers from all around the world. Uh we can usually
[48:20] all around the world. Uh we can usually as mentioned adhere to about 50 to 70%
[48:22] as mentioned adhere to about 50 to 70% of them uh through
[48:25] of them uh through the constraints and the furnitures that
[48:26] the constraints and the furnitures that we embed into your plan library.
[48:29] we embed into your plan library. So, I think we'll be able to work with
[48:31] So, I think we'll be able to work with the Chilean
[48:32] the Chilean norms as well.
[48:39] Next question is if you can split the screen in the Finch workflow to view
[48:41] screen in the Finch workflow to view both the floor plan and the 3D view of
[48:44] both the floor plan and the 3D view of the rooms model simultaneously. I think
[48:46] the rooms model simultaneously. I think we've done this, right?
[48:48] we've done this, right? Yeah, we had it earlier on but we
[48:50] Yeah, we had it earlier on but we removed it.
[48:51] removed it. So, you cannot.
[48:54] So, you cannot. Okay, not anymore.
[49:01] Uh next question is if you have already designed a layout in Revit but want to
[49:02] designed a layout in Revit but want to have more layout options, will you be
[49:04] have more layout options, will you be able to do that in Finch for the same
[49:06] able to do that in Finch for the same model?
[49:07] model? I think if you want more layout options,
[49:09] I think if you want more layout options, I would use the feature that Amelia
[49:11] I would use the feature that Amelia demoed here today. You can generate
[49:13] demoed here today. You can generate floor plans directly into Revit.
[49:20] And then the final one, is it possible to work with prompts
[49:22] is it possible to work with prompts offering flexibility in the projects
[49:24] offering flexibility in the projects switching between different typologies
[49:25] switching between different typologies but keeping the structure stability of
[49:27] but keeping the structure stability of the buildings in intelligent way? Also
[49:30] the buildings in intelligent way? Also in renovation projects, mix builds, etc.
[49:33] in renovation projects, mix builds, etc. Uh
[49:34] Uh regarding renovation projects, you can
[49:36] regarding renovation projects, you can upload
[49:37] upload existing structure to Finch and Finch
[49:39] existing structure to Finch and Finch can work around this.
[49:41] can work around this. Um
[49:42] Um and yeah, I mean Jesper showed a very
[49:45] and yeah, I mean Jesper showed a very simple prompt here just to generate an
[49:46] simple prompt here just to generate an office. Uh but usually for our
[49:48] office. Uh but usually for our customers, those are much longer, much
[49:50] customers, those are much longer, much more customized to to how they design.
[49:54] more customized to to how they design. So, yes.
[49:59] And when it comes to structure, of course, uh gridlines and so on.
[50:06] Good. I think it was all of the questions. Anything you'd like to add?
[50:08] questions. Anything you'd like to add? Jesper, maybe?
[50:10] Jesper, maybe? Maybe the last one. I mean, working with
[50:12] Maybe the last one. I mean, working with Nana Banana, you can also feed existing
[50:14] Nana Banana, you can also feed existing walls into the to to Nana Banana and
[50:17] walls into the to to Nana Banana and it's usually pretty good at working
[50:20] it's usually pretty good at working around them.
[50:25] No. Nothing more from me.
[50:27] Nothing more from me. So, thank you Thank you to everyone who
[50:29] So, thank you Thank you to everyone who attended here today. We will send out
[50:31] attended here today. We will send out the recording tomorrow and feel free to
[50:33] the recording tomorrow and feel free to reach out to us if you have any
[50:34] reach out to us if you have any questions around the what type of
[50:36] questions around the what type of project we support, if you have an
[50:38] project we support, if you have an upcoming project, or you think Finch
[50:39] upcoming project, or you think Finch could be a good fit.
[50:41] could be a good fit. Uh happy to help you get started.
[50:43] Uh happy to help you get started. Thank you.
[50:44] Thank you. Bye-bye.
```

## All frames

_Total: 50. Hero frames flagged with star._

* `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0001.jpg` (t=00:00)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0002.jpg` (t=00:03)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0003.jpg` (t=00:26)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0004.jpg` (t=01:34)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0005.jpg` (t=01:54)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0006.jpg` (t=03:26)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0007.jpg` (t=03:52)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0008.jpg` (t=04:38)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0009.jpg` (t=04:40)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0010.jpg` (t=05:25)
* `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0011.jpg` (t=05:54)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0012.jpg` (t=06:24)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0013.jpg` (t=10:10)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0014.jpg` (t=12:25)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0015.jpg` (t=12:41)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0016.jpg` (t=13:50)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0017.jpg` (t=14:31)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0018.jpg` (t=15:46)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0019.jpg` (t=16:05)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0020.jpg` (t=16:17)
* `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0021.jpg` (t=16:18)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0022.jpg` (t=16:21)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0023.jpg` (t=16:21)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0024.jpg` (t=16:23)
* `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0025.jpg` (t=16:24)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0026.jpg` (t=27:38)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0027.jpg` (t=27:39)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0028.jpg` (t=27:50)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0029.jpg` (t=27:50)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0030.jpg` (t=31:18)
* `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0031.jpg` (t=31:23)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0032.jpg` (t=32:20)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0033.jpg` (t=33:15)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0034.jpg` (t=33:31)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0035.jpg` (t=34:10)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0036.jpg` (t=34:14)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0037.jpg` (t=34:23)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0038.jpg` (t=35:13)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0039.jpg` (t=35:57)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0040.jpg` (t=36:27)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0041.jpg` (t=38:17)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0042.jpg` (t=38:29)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0043.jpg` (t=38:42)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0044.jpg` (t=39:21)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0045.jpg` (t=39:53)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0046.jpg` (t=39:55)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0047.jpg` (t=39:57)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0048.jpg` (t=42:00)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0049.jpg` (t=43:57)
  `C:\Praca\01 AI\HERMES\DOMKO_APP\ANALIZA_FINCH3D\frames\frame_0050.jpg` (t=44:20)
