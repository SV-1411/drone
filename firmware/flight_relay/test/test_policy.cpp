#include "flight_policy.h"
#include <cassert>
#include <iostream>
#include <limits>
using namespace vanni;
static constexpr double utc=1792135000.;
Telemetry good(uint32_t now=10000) {
    Telemetry t;
    t.heartbeat=t.position=t.gps=t.radio=t.power=t.system=now;
    t.home=t.extended=t.estimator=t.params=now;
    t.lat=t.homeLat=21.1;t.lon=t.homeLon=79.1;
    t.navSpeed=t.climbSpeed=t.descendSpeed=t.landSpeed=.5;
    t.voltage=12.2;t.batteryPct=90;t.gpsFix=3;t.satellites=12;
    t.rcOk=t.landed=t.prearmOk=t.ekfOk=t.linkFailsafeConfigured=true;
    return t;
}
Command valid() {
    Command c;std::strcpy(c.id,"approved-voice-1");c.verifiedVoice=true;
    c.lat=21.10009;c.lon=79.1;c.created=utc-2;c.expires=utc+58;return c;
}
Controller ready() {Controller c;c.cells=3;c.enabled=true;c.unlockedAt=10000;return c;}
void refresh(Telemetry& t,uint32_t now) {
    t.heartbeat=t.position=t.gps=t.radio=t.power=t.system=now;
    t.home=t.extended=t.estimator=t.params=now;
}
int main() {
    unsigned cases=0;
    {Controller c;auto t=good();assert(c.accept(valid(),t,10000,utc,false));assert(c.tick(t,10000).kind==Kind::None);++cases;}
    {auto c=ready();assert(c.accept(valid(),good(),130001,utc,false));++cases;}
    {auto c=ready();assert(c.accept(valid(),good(),10000,utc,true));++cases;}
    {auto c=ready();auto x=valid();x.expires=utc-1;assert(c.accept(x,good(),10000,utc,false));++cases;}
    {auto c=ready();auto x=valid();x.lat=std::numeric_limits<double>::quiet_NaN();assert(c.accept(x,good(),10000,utc,false));++cases;}
    {auto c=ready();auto x=valid();x.verifiedVoice=false;assert(c.accept(x,good(),10000,utc,false));++cases;}
    {auto c=ready();auto x=valid();x.lat+=.01;assert(c.accept(x,good(),10000,utc,false));++cases;}
    {auto c=ready();auto t=good();t.voltage=10.52;assert(c.accept(valid(),t,10000,utc,false));++cases;}
    {auto c=ready();auto t=good();t.radio=100;t.rcOk=false;assert(c.accept(valid(),t,10000,utc,false));++cases;}
    {auto c=ready();auto t=good();t.navSpeed=10;assert(c.accept(valid(),t,10000,utc,false));++cases;}
    {auto c=ready();auto t=good();t.linkFailsafeConfigured=false;assert(c.accept(valid(),t,10000,utc,false));++cases;}
    {auto c=ready();c.recoveryRequired=true;assert(c.accept(valid(),good(),10000,utc,false));++cases;}
    {auto c=ready();c.continuous=true;auto t=good(500000);
     assert(!c.accept(valid(),t,500000,utc,false));assert(c.enabled);
     c.state=State::Completed;auto next=valid();std::strcpy(next.id,"approved-voice-2");
     assert(!c.accept(next,t,500001,utc,false));++cases;}
    {auto c=ready();auto t=good();t.armed=true;assert(c.accept(valid(),t,10000,utc,false));++cases;}
    {auto c=ready();auto t=good();t.prearmOk=false;assert(c.accept(valid(),t,10000,utc,false));++cases;}
    {auto c=ready();auto t=good();assert(!c.accept(valid(),t,10000,utc,false));assert(c.tick(t,10000).kind==Kind::Guided);
     c.confirm(false,10001);assert(c.state==State::Failed);assert(c.tick(t,10002).kind==Kind::None);++cases;}
    {auto c=ready();auto t=good();assert(!c.accept(valid(),t,10000,utc,false));
     assert(c.tick(t,10000).kind==Kind::Guided);
     t.mode=4;assert(c.tick(t,10001).kind==Kind::Speed);
     c.confirm(true,10002);assert(c.tick(t,10003).kind==Kind::Arm);
     c.confirm(true,10004);t.armed=true;assert(c.tick(t,10005).kind==Kind::Takeoff);
     c.confirm(true,10006);t.altitude=.9;t.landed=false;
     assert(c.tick(t,10007).kind==Kind::Waypoint);assert(c.state==State::Outbound);
     t.lat=valid().lat;auto ret=c.tick(t,10008);assert(ret.kind==Kind::Waypoint);assert(c.state==State::Return);
     assert(ret.lat==21.1);t.lat=21.1;assert(c.tick(t,10009).kind==Kind::Land);
     t.mode=9;c.tick(t,10010);t.landed=true;t.armed=false;c.tick(t,10011);
     assert(c.state==State::Completed);assert(!c.enabled);++cases;}
    for (int why=0;why<4;why++) {
     auto c=ready();auto t=good();assert(!c.accept(valid(),t,10000,utc,false));
     c.enter(State::Outbound,10000);c.sawArmed=true;t.armed=true;t.mode=4;t.landed=false;t.altitude=1;
     if(why==0)t.voltage=9.7;if(why==1)t.ekfOk=false;if(why==2)t.rcOk=false;
     uint32_t now=why==3?130001:10001;refresh(t,now);
     assert(c.tick(t,now).kind==Kind::Land);assert(c.state==State::AbortLanding);++cases;
    }
    {auto c=ready();auto t=good();assert(!c.accept(valid(),t,10000,utc,false));c.sawArmed=true;
     c.enter(State::Outbound,10000);t.armed=true;t.mode=0;
     assert(c.tick(t,10001).kind==Kind::None);assert(c.state==State::Pilot);
     t.mode=4;assert(c.tick(t,10002).kind==Kind::None);++cases;}
    {auto c=ready();auto t=good();assert(!c.accept(valid(),t,10000,utc,false));c.sawArmed=true;
     c.enter(State::Outbound,10000);t.armed=true;t.mode=4;t.heartbeat=100;
     assert(c.tick(t,10001).kind==Kind::None);assert(c.busy());++cases;}
    std::cout<<cases<<" flight policy scenarios passed\n";
}
