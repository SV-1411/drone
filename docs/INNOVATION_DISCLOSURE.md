# VanniKawachh: Innovation Disclosure (Short Form)

**Title:** VanniKawachh, a Distributed AI Acoustic Intelligence and Autonomous
Drone Response Network for Women Safety
**Team:** Shivansh Verma, Saksham Sabadra, Rudra Thakur, Rohan Untawale
**Guide:** Dr. Aditya Turankar, Dept. of CSE, G H Raisoni College of
Engineering, Nagpur

---

## 1. Newness / Uniqueness of the Innovation

Existing women safety solutions put the burden on the victim. Apps, wearables,
and panic buttons only work if the person is carrying a charged device and can
reach it at the worst moment. Pure audio detection systems, on the other hand,
stop at detecting a scream and do nothing after that.

VanniKawachh is new because it is the first complete chain from the sound of
distress to a physical response, with the victim needing no device at all:

* The trigger is the human voice itself. Microphone nodes are mounted on public
  poles, so safety moves from the victim's body to public infrastructure.
* A two stage AI check keeps false alarms low. The node screens audio on device
  with MFCC plus a small CNN in under 50 ms, and a hub confirms with a deeper
  PANNs model fused with motion, light, and time of day.
* Alerts travel over an encrypted LoRa radio link with no SIM and no internet,
  so it works in cellular dead zones such as dark streets and forest roads.
* A drone responds on its own. It flies to the exact node coordinates, records
  evidence, and drops a first aid kit before ground help arrives.
* The same idea of verify before you act runs at every layer: sound, network
  command, and flight mode. The verified flight dispatch and failsafe logic are
  covered in two patent drafts in preparation.

## 2. Concept and Objective

**Concept.** Solar powered microphone nodes on roadside poles listen around the
clock. When someone shouts for help, two stages of AI confirm the distress, and
the system automatically sends the location to the police and launches a drone,
all without the victim touching a phone or an app.

**Objective.** Cut emergency response time from several minutes to a few seconds
in exactly the places where current tools fail, dark streets, forest stretches,
parking lots, and no signal areas, while keeping false alarms near zero, cost
low enough for city wide use, and privacy protected because audio is processed
on the node and only short event clips ever leave it.

## 8. Potential Areas of Application (Industry / Market)

* Women and public safety in cities, campuses, hostels, and transport hubs.
* Highway and forest corridor safety, where mobile coverage is weak.
* Industrial parks and critical infrastructure, for intrusion and accident
  detection by sound.
* Disaster and accident first response, reacting to calls for help.
* Elderly and patient monitoring in care homes and remote areas.
* Smart city safety infrastructure and law enforcement analytics.

## 9. Market Potential of the Idea / Innovation

Public safety is a large and growing area of spend. In India it is driven by
government programs such as the Nirbhaya Fund and the Safe City projects, and by
rising municipal investment in surveillance and emergency response. Globally,
personal safety devices, public safety analytics, and drone based response
("drone in a box") are all expanding markets.

VanniKawachh fits several buyers at once:

* Government and civic bodies (safe city programs, police, municipalities).
* Institutions (universities, hostels, industrial estates, hospitals).
* Transport and highway authorities for corridor safety.

The business model can combine a one time hardware sale of nodes, hubs, and
drones with a recurring monitoring and maintenance subscription. Because the
nodes are low cost and solar powered, the system is practical to deploy at city
scale, which is the main barrier for device based solutions today. This makes
the addressable market the broad safe city and public safety infrastructure
segment rather than only the personal gadget segment.
