#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Small auditable patches over the pinned upstream/kernel driver sources."""
from pathlib import Path

def replace_once(path, before, after):
    text = path.read_text()
    if after in text:
        return
    assert text.count(before) == 1, (str(path), 'source differs from reviewed input')
    path.write_text(text.replace(before, after, 1))

kernel = Path('/build/linux-6.12.114')
replace_once(kernel/'drivers/pci/controller/dwc/Kconfig',
    'config PCIE_AL\n\tbool "Amazon Annapurna Labs PCIe controller"\n\tdepends on OF && (ARM64 || COMPILE_TEST)',
    'config PCIE_AL\n\tbool "Amazon Annapurna Labs PCIe controller"\n\tdepends on OF && (ARM64 || ARCH_ALPINE || COMPILE_TEST)')
replace_once(kernel/'drivers/pci/controller/dwc/pcie-al.c',
    'static const struct of_device_id al_pcie_of_match[] = {\n',
    'static const struct of_device_id al_pcie_of_match[] = {\n'
    '\t/* AL314 board: legacy DBI at +0x2000, outbound control at +0x40. */\n'
    '\t{ .compatible = "qnap,ts431xeu-pcie" },\n')

ethernet = Path('/build/al_eth-standalone/src/al_eth_main.c')
replace_once(ethernet,
    '\tINIT_WORK(&adapter->reset_task, al_eth_reset_task);\n',
    '\tINIT_WORK(&adapter->reset_task, al_eth_reset_task);\n'
    '\t/* PHY-managed ports return early from open, but close cancels this work. */\n'
    '#ifdef CONFIG_ARCH_ALPINE\n'
    '\tINIT_DELAYED_WORK(&adapter->link_status_task, al_eth_link_status_task);\n'
    '#else\n'
    '\tINIT_DELAYED_WORK(&adapter->link_status_task, al_eth_link_status_task_nic);\n'
    '#endif\n')
# Initialization now happens at probe for every port, before any early open return.
text = ethernet.read_text()
for name in ('al_eth_link_status_task', 'al_eth_link_status_task_nic'):
    old = '\t\tINIT_DELAYED_WORK(&adapter->link_status_task,\n\t\t\t\t'+name+');\n'
    assert text.count(old) in (0, 1)
    text = text.replace(old, '')
ethernet.write_text(text)

# mdiobus_unregister already frees each registered PHY in modern kernels.
# Keep that bus registered across interface close/open; free it at PCI removal.
replace_once(ethernet,
    '\tmdiobus_unregister(adapter->mdio_bus);\n\tmdiobus_free(adapter->mdio_bus);\n\tphy_device_free(adapter->phydev);',
    '\tmdiobus_unregister(adapter->mdio_bus);\n\tmdiobus_free(adapter->mdio_bus);\n'
    '\tadapter->mdio_bus = NULL;\n\tadapter->phydev = NULL;')
replace_once(ethernet,
    '\t\tphy_disconnect(adapter->phydev);\n\t\tal_eth_mdiobus_teardown(adapter);',
    '\t\tphy_disconnect(adapter->phydev);\n\t\tadapter->phydev = NULL;')
replace_once(ethernet,
    '\tint ret;\n\n\tadapter->mdio_bus = mdiobus_alloc();',
    '\tint ret;\n\n'
    '\t/* Interface reopen reuses the bus retained by close. */\n'
    '\tif (adapter->mdio_bus)\n\t\treturn 0;\n\n'
    '\tadapter->mdio_bus = mdiobus_alloc();')
# A failed registration must not leave a dangling bus for PCI removal/retry.
text = ethernet.read_text()
text = text.replace('\t\t\tmdiobus_free(adapter->mdio_bus);\n\t\t\treturn i;',
                    '\t\t\tmdiobus_free(adapter->mdio_bus);\n'
                    '\t\t\tadapter->mdio_bus = NULL;\n\t\t\treturn i;')
text = text.replace('\tmdiobus_free(adapter->mdio_bus);\n\treturn -ENODEV;',
                    '\tmdiobus_free(adapter->mdio_bus);\n'
                    '\tadapter->mdio_bus = NULL;\n\treturn -ENODEV;')
ethernet.write_text(text)
replace_once(ethernet,
    '\tunregister_netdev(dev);\n\n\tal_eth_sysfs_terminate(&pdev->dev);',
    '\tunregister_netdev(dev);\n#ifdef CONFIG_PHYLIB\n'
    '\tal_eth_mdiobus_teardown(adapter);\n#endif\n\n'
    '\tal_eth_sysfs_terminate(&pdev->dev);')

# Linux 6.12 phy_stop() suspends the PHY. Drain MAC/UDMA while its clocks
# still run, before phy_stop/disconnect can power down the RGMII interface.
# Serialize against adjust_link using the same PHY lock held by phylib.
replace_once(ethernet,
    '#ifdef CONFIG_PHYLIB\n\t/** Stop PHY & MDIO BUS */\n',
    '#ifdef CONFIG_PHYLIB\n'
    '\tif (adapter->phydev) {\n'
    '\t\tmutex_lock(&adapter->phydev->lock);\n'
    '\t\tif (adapter->up)\n'
    '\t\t\tal_eth_down(adapter);\n'
    '\t\tmutex_unlock(&adapter->phydev->lock);\n'
    '\t}\n'
    '\t/** Stop PHY & MDIO BUS only after DMA is quiescent. */\n')
replace_once(ethernet,
    '\tint force_1000_base_x = false;\n\n\tif (phydev->link) {',
    '\tint force_1000_base_x = false;\n\n'
    '\t/* Close drains DMA under the PHY lock before stopping phylib. */\n'
    '\tif (!adapter->up)\n\t\treturn;\n\n'
    '\tif (phydev->link) {')

# Reopen must restore the retained PHY's clock before FLR/MAC/UDMA init.
# phy_connect() below resumes it too, but that happens after al_eth_up().
replace_once(ethernet,
    '\tnetif_carrier_off(netdev);\n\n\t/* Notify the stack of the actual queue counts. */',
    '\tnetif_carrier_off(netdev);\n\n'
    '#ifdef CONFIG_PHYLIB\n'
    '\tif (adapter->phy_exist && adapter->mdio_bus) {\n'
    '\t\tstruct phy_device *phydev = phy_find_first(adapter->mdio_bus);\n'
    '\t\tif (!phydev)\n\t\t\treturn -ENODEV;\n'
    '\t\trc = phy_resume(phydev);\n'
    '\t\tif (rc)\n\t\t\treturn rc;\n'
    '\t}\n'
    '#endif\n\n'
    '\t/* Notify the stack of the actual queue counts. */')
