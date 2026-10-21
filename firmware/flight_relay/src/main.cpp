#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <time.h>
#include <ardupilotmega/mavlink.h>
#include "flight_policy.h"
#include "gts_roots.h"

using namespace vanni;
constexpr uint8_t OUR_SYS=246, OUR_COMP=191;
constexpr int RX_PIN=44, TX_PIN=43;
constexpr uint32_t BAUD=57600;
constexpr char RELAY[]="https://vannikawachh-hub.onrender.com";
HardwareSerial pixhawk(1);
Preferences prefs;
Controller controller;
Telemetry telemetry;
String wifiSsid,wifiPassword,operatorKey;
uint8_t fcSys=0,fcComp=1;
uint32_t lastHeartbeat=0,lastRequest=0,lastParams=0,lastStatus=0;
uint16_t awaitingCommand=0;
uint32_t awaitingAt=0;
bool dirtyResult=false,networkBusy=false;
String pendingId,pendingStatus,pendingDetail;
State previousState=State::Idle;
float gcsEnable=0,gcsSys=0;
uint32_t paramTimes[6]={};
uint32_t rxPackets=0,txPackets=0,rxBytes=0;
int relayHttp=0;
struct NetworkJob {uint8_t type;char id[64];char status[16];char detail[241];};
struct NetworkReply {uint8_t type;int http;bool hasCommand;Command command;char node[96];};
QueueHandle_t jobs,replies;
bool commandInFlight=false;
bool receiverHealthy=true;
uint32_t lastPoll=0;

const char* stateName(State state) {
    switch(state) {
    case State::Idle:return "IDLE";case State::Guided:return "GUIDED";
    case State::Speed:return "SPEED";case State::Arm:return "ARM";
    case State::Takeoff:return "TAKEOFF";case State::Outbound:return "OUTBOUND";
    case State::Return:return "RETURN";case State::Landing:return "LANDING";
    case State::AbortLanding:return "ABORT_LANDING";case State::Pilot:return "PILOT_OR_FAILSAFE";
    case State::Completed:return "COMPLETED";default:return "FAILED";
    }
}
void sendMessage(const mavlink_message_t& m) {
    uint8_t b[MAVLINK_MAX_PACKET_LEN];auto n=mavlink_msg_to_send_buffer(b,&m);
    pixhawk.write(b,n);++txPackets;
}
void commandLong(uint16_t cmd,float p1=0,float p2=0,float p3=0,float p4=0,
                 float p5=0,float p6=0,float p7=0,bool track=false) {
    if(!fcSys)return;
    mavlink_message_t m;
    mavlink_msg_command_long_pack(OUR_SYS,OUR_COMP,&m,fcSys,fcComp,cmd,0,p1,p2,p3,p4,p5,p6,p7);
    if(track){awaitingCommand=cmd;awaitingAt=millis();}
    sendMessage(m);
}
void requestParam(const char* name) {
    mavlink_message_t m;
    mavlink_msg_param_request_read_pack(OUR_SYS,OUR_COMP,&m,fcSys,fcComp,name,-1);
    sendMessage(m);
}
void handleParam(const mavlink_param_value_t& p,uint32_t now) {
    char name[17]={};memcpy(name,p.param_id,16);float v=p.param_value;
    if(!isfinite(v))return;
    if(!strcmp(name,"WP_SPD")||!strcmp(name,"WPNAV_SPEED")) {
        telemetry.navSpeed=!strcmp(name,"WPNAV_SPEED")?v*.01f:v;paramTimes[0]=now;
    }else if(!strcmp(name,"WP_SPD_UP")||!strcmp(name,"WPNAV_SPEED_UP")){
        telemetry.climbSpeed=!strcmp(name,"WPNAV_SPEED_UP")?v*.01f:v;paramTimes[1]=now;
    }else if(!strcmp(name,"WP_SPD_DN")||!strcmp(name,"WPNAV_SPEED_DN")){
        telemetry.descendSpeed=!strcmp(name,"WPNAV_SPEED_DN")?v*.01f:v;paramTimes[2]=now;
    }else if(!strcmp(name,"LAND_SPD_MS")||!strcmp(name,"LAND_SPEED")){
        telemetry.landSpeed=!strcmp(name,"LAND_SPEED")?v*.01f:v;paramTimes[3]=now;
    }else if(!strcmp(name,"FS_GCS_ENABLE")){gcsEnable=v;paramTimes[4]=now;}
    else if(!strcmp(name,"MAV_GCS_SYSID")||!strcmp(name,"SYSID_MYGCS")){gcsSys=v;paramTimes[5]=now;}
    bool all=true;for(auto stamp:paramTimes)all=all&&fresh(now,stamp,15000);
    telemetry.params=all?now:0;
    telemetry.linkFailsafeConfigured=int(gcsEnable)==5 && int(gcsSys)==OUR_SYS;
}
void receiveMavlink() {
    static mavlink_message_t m;static mavlink_status_t parser{};
    while(pixhawk.available()) {
        const auto byte=pixhawk.read();++rxBytes;
        if(!mavlink_parse_char(MAVLINK_COMM_0,byte,&m,&parser))continue;
        if(m.msgid==MAVLINK_MSG_ID_HEARTBEAT) {
            mavlink_heartbeat_t h;mavlink_msg_heartbeat_decode(&m,&h);
            if(h.autopilot!=MAV_AUTOPILOT_ARDUPILOTMEGA || h.type==MAV_TYPE_GCS || m.compid!=1)continue;
            if(fcSys && m.sysid!=fcSys)continue;fcSys=m.sysid;fcComp=m.compid;
            telemetry.heartbeat=millis();telemetry.armed=h.base_mode&MAV_MODE_FLAG_SAFETY_ARMED;
            telemetry.mode=h.custom_mode;telemetry.critical=h.system_status>=MAV_STATE_CRITICAL;
        }
        if(!fcSys || m.sysid!=fcSys || m.compid!=fcComp)continue;
        ++rxPackets;uint32_t now=millis();
        switch(m.msgid) {
        case MAVLINK_MSG_ID_GLOBAL_POSITION_INT:{
            mavlink_global_position_int_t p;mavlink_msg_global_position_int_decode(&m,&p);
            telemetry.lat=p.lat/1e7;telemetry.lon=p.lon/1e7;
            telemetry.altitude=p.relative_alt*.001f;telemetry.position=now;break;}
        case MAVLINK_MSG_ID_GPS_RAW_INT:{
            mavlink_gps_raw_int_t p;mavlink_msg_gps_raw_int_decode(&m,&p);
            telemetry.gpsFix=p.fix_type;telemetry.satellites=p.satellites_visible;
            telemetry.gps=now;break;}
        case MAVLINK_MSG_ID_SYS_STATUS:{
            mavlink_sys_status_t p;mavlink_msg_sys_status_decode(&m,&p);
            telemetry.voltage=p.voltage_battery==UINT16_MAX?0:p.voltage_battery*.001f;
            telemetry.batteryPct=p.battery_remaining;telemetry.power=now;telemetry.system=now;
            constexpr uint32_t prearmBit=1UL<<28;
            telemetry.prearmOk=(p.onboard_control_sensors_health&prearmBit)!=0;
            receiverHealthy=!(p.onboard_control_sensors_enabled&MAV_SYS_STATUS_SENSOR_RC_RECEIVER) ||
                (p.onboard_control_sensors_health&MAV_SYS_STATUS_SENSOR_RC_RECEIVER);
            telemetry.rcOk=telemetry.rcOk && receiverHealthy;
            break;}
        case MAVLINK_MSG_ID_RC_CHANNELS:{
            mavlink_rc_channels_t p;mavlink_msg_rc_channels_decode(&m,&p);
            telemetry.rcOk=receiverHealthy && p.chancount>=4 && p.chan1_raw>=800 && p.chan1_raw<=2200 &&
                p.chan2_raw>=800 && p.chan2_raw<=2200 && p.chan3_raw>=800 && p.chan3_raw<=2200 &&
                p.chan4_raw>=800 && p.chan4_raw<=2200;telemetry.radio=now;break;}
        case MAVLINK_MSG_ID_HOME_POSITION:{
            mavlink_home_position_t p;mavlink_msg_home_position_decode(&m,&p);
            telemetry.homeLat=p.latitude/1e7;telemetry.homeLon=p.longitude/1e7;telemetry.home=now;break;}
        case MAVLINK_MSG_ID_EXTENDED_SYS_STATE:{
            mavlink_extended_sys_state_t p;mavlink_msg_extended_sys_state_decode(&m,&p);
            telemetry.landed=p.landed_state==MAV_LANDED_STATE_ON_GROUND;telemetry.extended=now;break;}
        case MAVLINK_MSG_ID_EKF_STATUS_REPORT:{
            mavlink_ekf_status_report_t p;mavlink_msg_ekf_status_report_decode(&m,&p);
            constexpr uint16_t required=EKF_ATTITUDE|EKF_VELOCITY_HORIZ|EKF_POS_HORIZ_ABS;
            telemetry.ekfOk=(p.flags&required)==required;telemetry.estimator=now;break;}
        case MAVLINK_MSG_ID_PARAM_VALUE:{
            mavlink_param_value_t p;mavlink_msg_param_value_decode(&m,&p);handleParam(p,now);break;}
        case MAVLINK_MSG_ID_COMMAND_ACK:{
            mavlink_command_ack_t p;mavlink_msg_command_ack_decode(&m,&p);
            if(p.command==awaitingCommand && fresh(now,awaitingAt,5000) &&
               (p.target_system==0 || p.target_system==OUR_SYS) &&
               (p.target_component==0 || p.target_component==OUR_COMP)) {
                if(p.result==MAV_RESULT_ACCEPTED){awaitingCommand=0;controller.confirm(true,now);}
                else if(p.result!=MAV_RESULT_IN_PROGRESS){awaitingCommand=0;controller.confirm(false,now);}
            }break;}
        case MAVLINK_MSG_ID_STATUSTEXT:{
            mavlink_statustext_t p;mavlink_msg_statustext_decode(&m,&p);
            char text[51]={};memcpy(text,p.text,50);
            if(p.severity<=MAV_SEVERITY_WARNING || strstr(text,"PreArm") || strstr(text,"Arm:")) {
                StaticJsonDocument<160> d;d["fc_message"]=text;serializeJson(d,Serial);Serial.println();
            }break;}
        }
    }
}
void readonlyTraffic(uint32_t now) {
    if(now-lastHeartbeat>=1000) {
        mavlink_message_t m;mavlink_msg_heartbeat_pack(OUR_SYS,OUR_COMP,&m,MAV_TYPE_GCS,
            MAV_AUTOPILOT_INVALID,0,0,MAV_STATE_ACTIVE);sendMessage(m);lastHeartbeat=now;
    }
    if(!fcSys || controller.busy())return;
    if(now-lastRequest>=10000){
        const uint16_t ids[]={MAVLINK_MSG_ID_GLOBAL_POSITION_INT,MAVLINK_MSG_ID_GPS_RAW_INT,
            MAVLINK_MSG_ID_SYS_STATUS,MAVLINK_MSG_ID_RC_CHANNELS,MAVLINK_MSG_ID_HOME_POSITION,
            MAVLINK_MSG_ID_EXTENDED_SYS_STATE,MAVLINK_MSG_ID_EKF_STATUS_REPORT};
        for(auto id:ids)commandLong(MAV_CMD_SET_MESSAGE_INTERVAL,id,1000000);
        commandLong(MAV_CMD_REQUEST_MESSAGE,MAVLINK_MSG_ID_HOME_POSITION);lastRequest=now;
    }
    if(now-lastParams>=10000){
        const char* names[]={"WP_SPD","WP_SPD_UP","WP_SPD_DN","LAND_SPD_MS","FS_GCS_ENABLE","MAV_GCS_SYSID"};
        for(auto name:names)requestParam(name);lastParams=now;
    }
}
void perform(const Action& a) {
    if(a.kind==Kind::None)return;
    // Only Controller::accept can leave the locked idle state.
    if(!controller.busy() || controller.recoveryRequired)return;
    switch(a.kind) {
    case Kind::Guided:commandLong(MAV_CMD_DO_SET_MODE,MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,4,0,0,0,0,0,true);break;
    case Kind::Speed:commandLong(MAV_CMD_DO_CHANGE_SPEED,1,kSpeedMs,-1,0,0,0,0,true);break;
    case Kind::Arm:commandLong(MAV_CMD_COMPONENT_ARM_DISARM,1,0,0,0,0,0,0,true);break;
    case Kind::Takeoff:commandLong(MAV_CMD_NAV_TAKEOFF,0,0,0,NAN,0,0,kAltitudeM,true);break;
    case Kind::Land:commandLong(MAV_CMD_DO_SET_MODE,MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,9,0,0,0,0,0,true);break;
    case Kind::Waypoint:{
        mavlink_message_t m;
        mavlink_msg_set_position_target_global_int_pack(OUR_SYS,OUR_COMP,&m,millis(),fcSys,fcComp,
            MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,0x0DF8,int32_t(lround(a.lat*1e7)),
            int32_t(lround(a.lon*1e7)),a.altitude,0,0,0,0,0,0,0,0);sendMessage(m);break;}
    default:break;
    }
}
void status() {
    if(!Serial)return;
    StaticJsonDocument<1100>d;uint32_t now=millis();
    d["firmware"]="vanni-flight-relay-1";d["chip"]="ESP32-S3";
    d["flight_locked"]=!controller.unlocked(now);d["state"]=stateName(controller.state);
    d["commissioned"]=controller.continuous;
    d["recovery_required"]=controller.recoveryRequired;
    d["wifi_configured"]=wifiSsid.length()>0;d["wifi_connected"]=WiFi.status()==WL_CONNECTED;
    d["operator_key_configured"]=operatorKey.length()>=32;d["cells"]=controller.cells;
    d["uart_rx"]=RX_PIN;d["uart_tx"]=TX_PIN;d["uart_baud"]=BAUD;
    d["mavlink_rx_packets"]=rxPackets;d["mavlink_tx_packets"]=txPackets;
    d["uart_rx_bytes"]=rxBytes;d["clock_synced"]=time(nullptr)>1700000000;d["relay_http"]=relayHttp;
    d["heartbeat_fresh"]=fresh(now,telemetry.heartbeat);d["armed"]=telemetry.armed;
    d["gps_fix"]=telemetry.gpsFix;d["satellites"]=telemetry.satellites;
    d["battery_v"]=telemetry.voltage;d["battery_pct"]=telemetry.batteryPct;
    d["preflight"]=preflight(telemetry,now,controller.cells)?preflight(telemetry,now,controller.cells):"basic checks pass";
    d["detail"]=controller.detail;d["max_target_m"]=kRadiusM;d["altitude_m"]=kAltitudeM;
    d["speed_ms"]=kSpeedMs;d["nav_speed_ms"]=telemetry.navSpeed;
    d["climb_speed_ms"]=telemetry.climbSpeed;d["descent_speed_ms"]=telemetry.descendSpeed;
    d["link_failsafe_ready"]=telemetry.linkFailsafeConfigured;
    serializeJson(d,Serial);Serial.println();
}
bool seen(const char* id){
    for(int i=0;i<32;++i){char k[8];snprintf(k,sizeof(k),"id%02d",i);if(prefs.getString(k)==id)return true;}return false;
}
bool remember(const char* id){
    uint32_t slot=prefs.getUInt("slot",0)%32;char k[8];snprintf(k,sizeof(k),"id%02u",unsigned(slot));
    return prefs.putString(k,id)>0 && prefs.putUInt("slot",(slot+1)%32)>0;
}
void result(const char* id,const char* outcome,const char* detail) {
    pendingId=id;pendingStatus=outcome;pendingDetail=detail;dirtyResult=true;
    prefs.putString("result_id",pendingId);prefs.putString("result_state",pendingStatus);
    prefs.putString("result_detail",pendingDetail);
}
void networkTask(void*) {
    WiFi.mode(WIFI_STA);if(wifiSsid.length())WiFi.begin(wifiSsid.c_str(),wifiPassword.c_str());
    configTime(0,0,"time.cloudflare.com","pool.ntp.org");
    uint32_t retry=0;
    for(;;){
        if(WiFi.status()!=WL_CONNECTED && wifiSsid.length() && millis()-retry>15000){WiFi.reconnect();retry=millis();}
        NetworkJob job;if(xQueueReceive(jobs,&job,pdMS_TO_TICKS(100))!=pdTRUE)continue;
        NetworkReply reply{};reply.type=job.type;reply.http=-1;
        if(WiFi.status()!=WL_CONNECTED || time(nullptr)<1700000000 || operatorKey.length()<32){
            xQueueSend(replies,&reply,portMAX_DELAY);continue;
        }
        WiFiClientSecure tls;tls.setCACert(VANNI_GTS_ROOTS);tls.setHandshakeTimeout(6);tls.setTimeout(6000);
        HTTPClient http;http.useHTTP10(true);http.setTimeout(6000);http.setConnectTimeout(4000);
        String path=job.type==1?"/edge/real-test/claim/next":
            job.type==2?String("/edge/real-test/result/")+job.id:"/edge/device/status";
        if(http.begin(tls,String(RELAY)+path)){
            http.addHeader("X-Operator-Key",operatorKey);
            http.addHeader("Content-Type","application/json");
            String body="{}";
            if(job.type==2){StaticJsonDocument<400>d;d["status"]=job.status;d["detail"]=job.detail;body="";serializeJson(d,body);}
            reply.http=job.type==3?http.GET():http.POST(body);
            if(reply.http==200 && job.type==1){
                // No unbounded stream allocation; accepted command responses fit within 2KB.
                if(http.getSize()>2048)reply.http=-2;
                else {StaticJsonDocument<2048>d;
                    if(deserializeJson(d,http.getStream()))reply.http=-3;
                    else if(!d["command"].isNull()){
                        JsonObject c=d["command"].as<JsonObject>();reply.hasCommand=true;
                        strlcpy(reply.command.id,c["id"]|"",sizeof(reply.command.id));
                        strlcpy(reply.node,c["node_id"]|"",sizeof(reply.node));
                        reply.command.lat=c["lat"].as<double>();reply.command.lon=c["lon"].as<double>();
                        reply.command.created=c["created"]|0.;reply.command.expires=c["expires_at"]|0.;
                        reply.command.verifiedVoice=!strncmp(reply.node,"phone-",6) &&
                            c["lat"].is<double>() && c["lon"].is<double>() &&
                            strlen(c["id"]|"")<sizeof(reply.command.id);
                    }
                }
            }
            if(reply.http==200 && job.type==2){StaticJsonDocument<256>d;
                if(deserializeJson(d,http.getStream()) || d["updated"]!=true)reply.http=409;
            }
            http.end();
        }
        xQueueSend(replies,&reply,portMAX_DELAY);
    }
}
void usbCommand(const String& line) {
    StaticJsonDocument<1800>d;
    if(deserializeJson(d,line)){Serial.println("{\"error\":\"invalid USB JSON\"}");return;}
    String op=d["op"]|"";
    if(op=="status"){status();return;}
    if(op=="lock") {controller.enabled=false;prefs.putBool("enabled",false);if(controller.busy())controller.abort("local LOCK",millis());Serial.println("{\"locked\":true}");return;}
    if(op=="configure"){
        if(controller.busy() || telemetry.armed){Serial.println("{\"error\":\"configuration refused while busy/armed\"}");return;}
        String ssid=d["ssid"]|wifiSsid,password=d["password"]|wifiPassword,token=d["operator_key"]|operatorKey;
        int cells=d["cells"]|controller.cells;
        if(ssid.length()>32 || password.length()>64 || token.length()>256 ||
           (token.length() && token.length()<32) || cells<0 || cells>6 || cells==1){Serial.println("{\"error\":\"invalid configuration\"}");return;}
        prefs.putString("ssid",ssid);prefs.putString("password",password);
        prefs.putString("opkey",token);prefs.putUInt("cells",cells);
        prefs.putBool("enabled",false);
        bool ok=prefs.getString("ssid")==ssid && prefs.getString("password")==password &&
            prefs.getString("opkey")==token && prefs.getUInt("cells",99)==unsigned(cells) && !prefs.getBool("enabled",true);
        Serial.println(ok?"{\"configured\":true,\"flight_locked\":true,\"restarting\":true}":"{\"error\":\"NVS write failed\"}");
        if(ok){Serial.flush();delay(200);ESP.restart();}return;
    }
    if(op=="authorize" || op=="commission"){
        const char* why=preflight(telemetry,millis(),controller.cells);
        if(controller.busy()||controller.recoveryRequired || why ||
           d["pilot_ready"]!=true || d["manual_flight_validated"]!=true || d["link_failsafe_tested"]!=true ||
           (op=="commission" && d["battery_calibrated"]!=true)){
            StaticJsonDocument<220>o;o["authorized"]=false;o["reason"]=why?why:"local readiness/recovery confirmation required";serializeJson(o,Serial);Serial.println();return;}
        controller.continuous=op=="commission";
        if(controller.continuous && prefs.putBool("enabled",true)==0){Serial.println("{\"error\":\"NVS write failed\"}");return;}
        if(!controller.continuous)prefs.putBool("enabled",false);
        controller.enabled=true;controller.unlockedAt=millis();
        Serial.println(controller.continuous?"{\"commissioned\":true,\"flight_locked\":false}":
            "{\"authorized\":true,\"one_mission\":true,\"expires_in_s\":120}");return;
    }
    if(op=="recover"){
        if(!fresh(millis(),telemetry.heartbeat)||telemetry.armed||!telemetry.landed){Serial.println("{\"error\":\"grounded disarmed telemetry required\"}");return;}
        if(prefs.putBool("active",false)==0){Serial.println("{\"error\":\"NVS write failed\"}");return;}
        controller.recoveryRequired=false;controller.state=State::Idle;controller.enabled=false;
        prefs.putBool("enabled",false);
        Serial.println("{\"recovered\":true,\"flight_locked\":true}");return;
    }
    if(op=="authcheck"&&!networkBusy){NetworkJob j{};j.type=3;if(xQueueSend(jobs,&j,0)==pdTRUE)networkBusy=true;return;}
    Serial.println("{\"error\":\"unknown operation or network busy\"}");
}
void setup(){
    Serial.begin(115200);delay(400);prefs.begin("vanni-flight",false);
    wifiSsid=prefs.getString("ssid");wifiPassword=prefs.getString("password");operatorKey=prefs.getString("opkey");
    controller.cells=prefs.getUInt("cells",0);controller.recoveryRequired=prefs.getBool("active",false);
    controller.continuous=prefs.getBool("enabled",false);
    controller.enabled=controller.continuous && !controller.recoveryRequired;
    pendingId=prefs.getString("result_id");pendingStatus=prefs.getString("result_state");
    pendingDetail=prefs.getString("result_detail");dirtyResult=pendingId.length()>0;
    pixhawk.setRxBufferSize(8192);pixhawk.begin(BAUD,SERIAL_8N1,RX_PIN,TX_PIN);
    jobs=xQueueCreate(2,sizeof(NetworkJob));replies=xQueueCreate(2,sizeof(NetworkReply));
    xTaskCreatePinnedToCore(networkTask,"cloud",12288,nullptr,1,nullptr,0);
    Serial.println("{\"boot\":\"vanni-flight-relay-1\"}");status();
}
void loop(){
    uint32_t now=millis();receiveMavlink();readonlyTraffic(now);
    static String line;
    while(Serial.available()){
        char c=Serial.read();if(c=='\n'){usbCommand(line);line="";}
        else if(c!='\r'){if(line.length()<1700)line+=c;else line="";}
    }
    Action action=controller.tick(telemetry,now);
    if(controller.state!=previousState){
        awaitingCommand=0;
        StaticJsonDocument<220>d;d["state"]=stateName(controller.state);d["detail"]=controller.detail;
        serializeJson(d,Serial);Serial.println();previousState=controller.state;
    }
    perform(action);
    if(controller.terminal()&&commandInFlight){
        // Keep a recovery lock if disarm/landing were never actually confirmed.
        if(fresh(now,telemetry.heartbeat)&&!telemetry.armed&&telemetry.landed&&fresh(now,telemetry.extended,5000))
            controller.recoveryRequired=prefs.putBool("active",false)==0;
        result(controller.command.id,controller.state==State::Completed?"completed":"rejected",controller.detail);
        commandInFlight=false;
    }
    NetworkReply reply;
    while(xQueueReceive(replies,&reply,0)==pdTRUE){
        networkBusy=false;
        relayHttp=reply.http;
        if(reply.type==3){StaticJsonDocument<120>d;d["relay_auth_ok"]=reply.http==200;d["http"]=reply.http;serializeJson(d,Serial);Serial.println();}
        if(reply.type==2 && reply.http==200){dirtyResult=false;prefs.remove("result_id");prefs.remove("result_state");prefs.remove("result_detail");}
        if(reply.type==1 && reply.http==200 && reply.hasCommand){
            if(!strcmp(reply.node,"operator-diagnostic")){
                String detail=String("ESP reached; ")+(fresh(now,telemetry.heartbeat)?"Pixhawk connected; ":"Pixhawk disconnected; ")+"flight locked="+(!controller.unlocked(now)?"yes":"no");
                result(reply.command.id,"completed",detail.c_str());
            }else{
                const bool duplicate=seen(reply.command.id);
                const char* why=controller.accept(reply.command,telemetry,now,time(nullptr),duplicate);
                if(why)result(reply.command.id,"rejected",why);
                else if(!remember(reply.command.id)||prefs.putBool("active",true)==0){
                    controller.recoveryRequired=true;
                    controller.abort("persistent command journal write failed",now);
                    result(reply.command.id,"rejected",controller.detail);
                }else commandInFlight=true;
            }
        }
    }
    if(!networkBusy && now-lastPoll>=2000 && operatorKey.length()>=32){
        NetworkJob j{};
        if(dirtyResult){j.type=2;strlcpy(j.id,pendingId.c_str(),sizeof(j.id));strlcpy(j.status,pendingStatus.c_str(),sizeof(j.status));strlcpy(j.detail,pendingDetail.c_str(),sizeof(j.detail));}
        else if(!controller.busy()){j.type=1;} // active flights never claim a second command
        if(j.type && xQueueSend(jobs,&j,0)==pdTRUE){networkBusy=true;lastPoll=now;}
    }
    if(now-lastStatus>=10000){status();lastStatus=now;}
    delay(2);
}
