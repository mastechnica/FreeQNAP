// SPDX-License-Identifier: GPL-2.0-or-later
/* TS-431XeU SPEC3 power-off, after the ordinary kernel shutdown path.
 * Based on the final UART handoff approach of Linux qnap-poweroff.c,
 * Copyright (C) 2012 Andrew Lunn <andrew@lunn.ch>.
 * No UART write occurs at load/unload. This is not a restart handler.
 */
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/reboot.h>
#include <linux/serial_reg.h>

static void __iomem *uart;
static struct sys_off_handler *handler;
static u32 uart_clock;
static bool ready;
module_param(ready, bool, 0444);
MODULE_PARM_DESC(ready, "Final power-off callback registered; never a userspace trigger");

static int final_poweroff(struct sys_off_data *data)
{
 static const u8 command[] = { '@', 'C', '0', 0x33 };
 unsigned int divisor = DIV_ROUND_CLOSEST(uart_clock, 16U * 115200U);
 u32 status;
 int i;
 /* MD reboot notifiers, device shutdown and syscore shutdown have run.
  * CPUs/interrupts are stopped: bounded MMIO polling only, no sleeping API.
  */
 pr_emerg("FreeQNAP: final kernel power-off after RAID/device shutdown; SPEC3 UART1\n");
 writel(0x83, uart + (UART_LCR << 2));
 writel(divisor & 0xff, uart + (UART_DLL << 2));
 writel((divisor >> 8) & 0xff, uart + (UART_DLM << 2));
 writel(UART_LCR_WLEN8, uart + (UART_LCR << 2));
 writel(0, uart + (UART_IER << 2));
 writel(0, uart + (UART_FCR << 2));
 writel(0, uart + (UART_MCR << 2));
 for (i = 0; i < ARRAY_SIZE(command); i++) {
  if (readl_poll_timeout_atomic(uart + (UART_LSR << 2), status,
       status & UART_LSR_THRE, 10, 100000)) {
   pr_emerg("FreeQNAP: final UART transmit timeout; manual power check required\n");
   return NOTIFY_DONE;
  }
  writel(command[i], uart + (UART_TX << 2));
 }
 readl_poll_timeout_atomic(uart + (UART_LSR << 2), status,
      status & UART_LSR_TEMT, 10, 100000);
 mdelay(1000);
 pr_emerg("FreeQNAP: power removal not observed; inspect chassis before intervention\n");
 return NOTIFY_DONE;
}

static int __init freeqnap_poweroff_init(void)
{
 struct device_node *node;
 struct resource resource;
 u32 shift, width;
 int result;
 if (!of_machine_is_compatible("qnap,ts-431xeu"))
  return -ENODEV;
 node = of_find_node_by_path("serial1");
 if (!node)
  return -ENODEV;
 result = of_address_to_resource(node, 0, &resource);
 if (result || resource.start != 0xfd884000 || resource_size(&resource) != 0x1000 ||
     of_property_read_u32(node, "reg-shift", &shift) || shift != 2 ||
     of_property_read_u32(node, "reg-io-width", &width) || width != 4 ||
     of_property_read_u32(node, "clock-frequency", &uart_clock) || uart_clock != 375000000) {
  of_node_put(node);
  return -EINVAL;
 }
 of_node_put(node);
 /* Like upstream qnap-poweroff: share the UART mapping, touching it only
  * after the ordinary serial driver has shut down. Never claim its region.
  */
 uart = ioremap(resource.start, resource_size(&resource));
 if (!uart)
  return -ENOMEM;
 handler = register_sys_off_handler(SYS_OFF_MODE_POWER_OFF, SYS_OFF_PRIO_DEFAULT,
           final_poweroff, NULL);
 if (IS_ERR(handler)) {
  result = PTR_ERR(handler);
  iounmap(uart);
  return result;
 }
 ready = true;
 pr_info("FreeQNAP: guarded SPEC3 final power-off registered; UART untouched\n");
 return 0;
}

static void __exit freeqnap_poweroff_exit(void)
{
 ready = false;
 unregister_sys_off_handler(handler);
 iounmap(uart);
}
module_init(freeqnap_poweroff_init);
module_exit(freeqnap_poweroff_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TS-431XeU final SPEC3 power-off after kernel RAID shutdown");
