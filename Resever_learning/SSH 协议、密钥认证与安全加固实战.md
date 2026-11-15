---
title: SSH 协议、密钥认证与安全加固实战
date: 2026-09-29T10:30:00+08:00
lastmod: 2026-09-29T10:30:00+08:00
---

# SSH 协议、密钥认证与安全加固实战

# SSH 协议、密钥认证与安全加固实战：从握手到故障排查

## 0x00 前言

SSH（Secure Shell）不是单纯的“远程登录命令”，而是一套建立加密通道、验证服务器身份、认证客户端身份并承载终端、文件传输和端口转发的协议族。真正掌握 SSH，需要把客户端命令、服务端配置、密钥文件、网络握手、日志记录和权限边界放在同一条链路中理解。

本文按一次连接的实际顺序展开：先定位配置，再拆解握手和认证，随后整理密钥管理、跳板机、转发、SFTP/SCP、安全加固、审计和常见故障。示例默认用于本人或已授权主机的运维与实验环境。

## 0x01 SSH 组件与文件地图

```text
客户端：ssh、scp、sftp、ssh-keygen、ssh-agent、ssh-add
服务端：sshd、sshd_config、authorized_keys
用户配置：~/.ssh/config
用户私钥：~/.ssh/id_ed25519 或自定义文件
用户公钥：*.pub
主机指纹缓存：~/.ssh/known_hosts
服务端主机密钥：/etc/ssh/ssh_host_*
常见日志：journalctl -u ssh/sshd、/var/log/auth.log、/var/log/secure
```

客户端私钥证明“你是谁”，服务端主机密钥证明“服务器是谁”。两者角色不同：删除 known_hosts 不能修复客户端认证失败，替换用户私钥也不能消除主机指纹变更告警。

## 0x02 一次 SSH 连接经历了什么

```text
1. TCP 建连：客户端连接服务端 22/TCP 或自定义端口
2. 版本协商：双方交换 SSH-2.0 标识
3. 算法协商：确定 KEX、HostKey、Cipher、MAC/AEAD、Compression
4. 密钥交换：派生会话密钥，建立加密与完整性保护
5. 主机认证：客户端校验服务器主机密钥指纹
6. 用户认证：公钥、密码、键盘交互、证书等
7. 通道建立：shell、exec、subsystem、forwarding
8. 会话关闭：通道退出并释放连接
```

抓包时通常只能看到 TCP、SSH 版本字符串和加密后的数据长度，认证口令、终端内容与传输文件不会以明文出现。若握手前就失败，应优先检查 TCP、端口、ACL 和监听状态；若握手后失败，再看算法、指纹和认证日志。

## 0x03 先学会读调试输出

```bash
ssh -V
ssh -vvv user@host
ssh -G user@host | less
sshd -T | less
sshd -t
```

ssh -vvv 展示客户端实际读取了哪些配置、解析到哪个地址、尝试了哪些身份文件、服务端接受了哪些认证方法。ssh -G 输出合并后的最终客户端配置。服务端修改配置前先执行 sshd -t 做语法检查，sshd -T 可查看展开后的有效配置，避免“改了文件但实例没有读取”的误判。

## 0x04 客户端配置：把长命令变成主机别名

```sshconfig
Host lab-gw
    HostName 203.0.113.10
    User ops
    Port 2222
    IdentityFile ~/.ssh/lab_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host lab-internal
    HostName 10.10.20.15
    User analyst
    ProxyJump lab-gw
    IdentityFile ~/.ssh/lab_internal_ed25519
```

配置按“先得到的值优先”处理时容易产生误解，通用 Host * 通常放在后面，具体主机放在前面。排查时用 ssh -G lab-internal 检查 hostname、user、port、proxyjump 和 identityfile 的最终值。

## 0x05 主机指纹与 known_hosts

```bash
ssh-keygen -F example.com
ssh-keygen -R example.com
ssh-keyscan -t ed25519 example.com
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

首次连接显示的指纹应通过可信渠道核对，例如云控制台、资产系统或管理员面对面确认。出现 REMOTE HOST IDENTIFICATION HAS CHANGED 时，不应直接清空整个 known_hosts；先确认服务器是否重装、IP 是否复用、DNS 是否被改动或链路中是否存在代理，再只删除对应条目。ssh-keyscan 只能收集公钥，不能自动证明该公钥可信。

## 0x06 密钥类型与生成建议

```bash
ssh-keygen -t ed25519 -a 64 -C "mary@workstation-2026-09-29"
ssh-keygen -t rsa -b 3072 -o -a 64 -C "legacy-compatible"
ssh-keygen -lf ~/.ssh/id_ed25519.pub
ssh-keygen -y -f ~/.ssh/id_ed25519 > recovered.pub
```

新环境优先考虑 Ed25519；需要兼容较旧设备时再评估 RSA。私钥应设置口令，-a 提高私钥口令派生的计算成本，-o 使用现代私钥格式。公钥可以公开，私钥必须本地保护并纳入备份策略；不要在聊天、工单或代码仓库中粘贴私钥。

## 0x07 authorized_keys 的权限与约束

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
chown -R "$USER:$USER" ~/.ssh
restorecon -Rv ~/.ssh    # SELinux 系统按需执行
```

公钥认证失败时，最常见的问题不是算法，而是目录归属、权限、家目录可写性、SELinux 上下文或服务端读取了不同的 AuthorizedKeysFile。服务端会主动拒绝“其他用户可篡改”的密钥文件。

```text
from="198.51.100.0/24",restrict,command="/usr/local/bin/readonly-backup" ssh-ed25519 AAAA... backup-key
```

authorized_keys 可为单把密钥增加来源地址、强制命令、禁止 PTY 和禁止转发等限制。对自动化账号，应尽量使用最小权限的专用密钥，而不是复用个人登录密钥。

## 0x08 ssh-agent：便利性与边界

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
ssh-add -l
ssh-add -D
```

ssh-agent 保存的是解密后的密钥使用能力，而不是把私钥文件复制到远端。启用 AgentForwarding 后，远端可通过转发套接字请求本地 agent 签名；被入侵的跳板机可能滥用这一能力。因此默认关闭代理转发，优先使用 ProxyJump 或为跳板链路配置独立密钥。

## 0x09 服务端 sshd_config 加固基线

```text
Port 2222
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers ops analyst
AllowAgentForwarding no
AllowTcpForwarding no
X11Forwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
LogLevel VERBOSE
```

基线必须结合业务调整。关闭密码认证前，先保留一个已验证的管理会话，并从第二个终端确认公钥登录成功；变更端口时同步检查防火墙、安全组、SELinux 端口标签和监控。不要为了“加固”盲目写死算法列表，除非已完成客户端兼容性盘点和回滚预案。

## 0x0A Match：按用户、来源和组细分策略

```text
Match Group sftp-only
    ChrootDirectory %h
    ForceCommand internal-sftp
    DisableForwarding yes
    PermitTTY no

Match User breakglass Address 198.51.100.10
    PasswordAuthentication yes
    AuthenticationMethods publickey,password
```

Match 块会影响后续配置作用域，编辑时要清楚条件从哪里开始。使用 sshd -T -C user=ops,host=server,addr=198.51.100.20 查看特定连接条件下的最终配置，比只阅读文件更可靠。

## 0x0B 跳板机与 ProxyJump

```bash
ssh -J ops@bastion.example.com analyst@10.10.20.15
scp -o ProxyJump=ops@bastion.example.com report.txt analyst@10.10.20.15:/tmp/
sftp -o ProxyJump=ops@bastion.example.com analyst@10.10.20.15
```

ProxyJump 让客户端通过跳板机转发到内网目标，私钥仍可留在本地，通常比先登录跳板机再手工二次登录更清晰。跳板机应单独审计，限制可达网段、会话类型和转发能力。

## 0x0C 端口转发：L、R、D 的方向

```bash
# 本地转发：访问本机 127.0.0.1:15432，流量经 SSH 到 db.internal:5432
ssh -N -L 127.0.0.1:15432:db.internal:5432 user@gateway

# 远程转发：服务端监听 18080，流量回到客户端的 127.0.0.1:8080
ssh -N -R 127.0.0.1:18080:127.0.0.1:8080 user@server

# 动态转发：本机建立 SOCKS5 代理
ssh -N -D 127.0.0.1:1080 user@gateway
```

判断方向时先找“监听端”：-L 在客户端监听，-R 在服务端监听，-D 在客户端提供 SOCKS。生产环境应绑定 127.0.0.1 并明确 PermitOpen、PermitListen 和 AllowTcpForwarding，避免无意暴露到所有网卡。

## 0x0D SCP、SFTP 与 rsync

```bash
scp -p local.bin user@host:/srv/upload/
sftp user@host
rsync -aHAX --info=progress2 -e "ssh -p 2222" ./data/ user@host:/srv/data/
```

现代 OpenSSH 的 scp 通常使用 SFTP 协议传输，但旧设备行为可能不同。需要断点续传、增量同步和属性保留时优先考虑 rsync over SSH；受限文件交换场景可使用 internal-sftp、ChrootDirectory 和独立目录权限。

## 0x0E SSH 证书：规模化密钥管理

```bash
# CA 签发用户证书示例
ssh-keygen -s user_ca -I mary-ops -n ops -V +8h mary_ed25519.pub

# 查看证书内容
ssh-keygen -L -f mary_ed25519-cert.pub
```

SSH 证书不是 X.509 证书。服务端信任用户 CA 后，可按 principal 和有效期验证用户证书，避免在大量服务器上逐台分发公钥。主机证书也能降低 known_hosts 管理成本。CA 私钥应离线或由受控签发系统保护，短有效期证书更利于撤销和审计。

## 0x0F 日志与审计定位

```bash
journalctl -u ssh --since "2026-09-29 00:00:00"
journalctl -u sshd -f
tail -f /var/log/auth.log
tail -f /var/log/secure
last -ai
lastb -ai
```

客户端日志回答“我尝试了什么”，服务端日志回答“服务器为什么接受或拒绝”。审计时重点关联时间、源 IP、用户名、认证方法、密钥指纹、会话开始与结束、sudo 记录和文件传输路径。仅凭一次 Failed password 不能判断入侵成功，应继续确认 Accepted、会话命令和后续行为。

## 0x10 常见报错对照表

```text
Connection timed out：路由、ACL、安全组、防火墙或地址错误
Connection refused：目标可达，但端口无监听或被主动拒绝
No route to host：路由、网关或中间设备返回不可达
Host key verification failed：主机指纹未通过校验
Permission denied (publickey)：密钥未被接受、用户错误或权限/策略问题
Too many authentication failures：agent 中密钥过多，配合 IdentitiesOnly yes
Bad owner or permissions：本地私钥或配置文件权限过宽
no matching host key type：新旧客户端算法兼容问题
subsystem request failed：SFTP 子系统配置或路径错误
```

## 0x11 分层排障流程

```text
第一层：DNS/IP 是否正确，ping 结果仅作参考
第二层：目标端口是否可达，服务是否监听正确地址
第三层：SSH 版本与算法是否完成协商
第四层：主机指纹是否可信且与资产记录一致
第五层：用户名、密钥、证书、密码和 MFA 是否匹配
第六层：家目录、.ssh、authorized_keys 权限与上下文
第七层：Match、AllowUsers/Groups、PAM、Shell、过期策略
第八层：PTY、SFTP、转发或命令通道是否被策略限制
```

每次只改变一个变量，并保留完整的 ssh -vvv 与服务端日志时间窗口。不要同时更换端口、密钥、用户名和跳板路径，否则即使恢复连接，也很难确认根因。

## 0x12 安全运维检查清单

```text
1. 主机指纹通过独立渠道核对
2. 私钥使用强口令并限制文件权限
3. 不在多台主机复用高权限密钥
4. 自动化密钥配置来源、命令和转发限制
5. 禁止直接 root 登录，管理操作使用 sudo 留痕
6. 公钥登录验证成功后再关闭密码认证
7. 跳板机、VPN、安全组和 sshd 策略共同限制来源
8. 默认关闭 AgentForwarding、X11 和不必要的 TCP 转发
9. 定期清理离职人员、公钥、证书 principal 和过期账号
10. 监控异常来源、失败频率、成功登录和配置变更
11. 修改配置前执行 sshd -t，并准备现有会话回滚
12. 备份 sshd_config、主机密钥和授权清单
```

## 0x13 实战：安全上线一台新 SSH 主机

```text
步骤一：控制台确认主机密钥指纹
步骤二：创建普通管理用户并配置 sudo
步骤三：写入独立公钥并修正权限
步骤四：从第二终端验证公钥登录
步骤五：设置 AllowUsers/Groups 与来源网络限制
步骤六：关闭 root 直登和不需要的认证方式
步骤七：限制转发、SFTP、PTY 等能力
步骤八：执行 sshd -t 后平滑重载服务
步骤九：验证新旧会话、文件传输和跳板链路
步骤十：接入日志、告警、资产和密钥轮换流程
```

## 0x14 总结

SSH 的核心不是背诵参数，而是建立四条清晰边界：服务器身份由主机密钥确认，用户身份由认证材料确认，会话能力由通道与转发策略限制，操作结果由日志和审计记录验证。

```text
连接问题：先网络，后协议
身份问题：先主机指纹，后用户认证
权限问题：先文件归属，后 sshd 策略
安全问题：先缩小来源，再缩小账号与通道能力
变更问题：先验证、保留会话，再重载与回滚
```

后续实验建议准备三台虚拟机：客户端、跳板机和内网服务器。分别记录直连、ProxyJump、本地转发、SFTP-only、密钥撤销和主机密钥更换时的 ssh -vvv 输出与服务端日志，把“命令—握手阶段—配置项—日志证据”四者对应起来。
