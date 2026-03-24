const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TinyHubMarketV3 (L2)", function () {
  let market, token, owner, settler, outsider;

  beforeEach(async function () {
    [owner, settler, outsider] = await ethers.getSigners();

    // Deploy MarketV3
    const MarketV3 = await ethers.getContractFactory("TinyHubMarketV3");
    market = await MarketV3.deploy();
    await market.waitForDeployment();

    // Deploy TokenL2
    const TokenL2 = await ethers.getContractFactory("TinyHubTokenL2");
    token = await TokenL2.deploy();
    await token.waitForDeployment();

    // Authorize settler
    await market.setSettler(settler.address, true);
    await token.setMinter(settler.address, true);
  });

  describe("Access Control", function () {
    it("owner can authorize settlers", async function () {
      expect(await market.settlers(settler.address)).to.equal(true);
    });

    it("non-owner cannot authorize settlers", async function () {
      await expect(
        market.connect(outsider).setSettler(outsider.address, true)
      ).to.be.revertedWith("Only owner");
    });

    it("non-settler cannot list resources", async function () {
      await expect(
        market.connect(outsider).listResource("s1", "IL_D91", 100, 50, 0)
      ).to.be.revertedWith("Only settler");
    });

    it("settler can list resources", async function () {
      await market.connect(settler).listResource("s1", "IL_D91", 100, 50, 0);
      expect(await market.tradeCount()).to.equal(1);
    });

    it("owner can revoke settler", async function () {
      await market.setSettler(settler.address, false);
      await expect(
        market.connect(settler).listResource("s1", "IL_D91", 100, 50, 0)
      ).to.be.revertedWith("Only settler");
    });
  });

  describe("Atomic Settlement", function () {
    it("settleTrade creates and settles in one tx", async function () {
      await market.connect(settler).settleTrade(
        "msg-001", "station-1", "IL_D91", 1000, 50, 0
      );

      expect(await market.tradeCount()).to.equal(1);
      const trade = await market.trades(1);
      expect(trade.stationId).to.equal("station-1");
      expect(trade.district).to.equal("IL_D91");
      expect(trade.status).to.equal(1); // Settled
      expect(trade.amount).to.equal(1000);
    });

    it("settleBridge creates a bridged trade", async function () {
      await market.connect(settler).settleBridge(
        "msg-002", "station-2", "IL_D91", "McHenry_D63", 500, 60, 0
      );

      expect(await market.tradeCount()).to.equal(1);
      const trade = await market.trades(1);
      expect(trade.status).to.equal(2); // Bridged
    });

    it("district counters update correctly", async function () {
      await market.connect(settler).settleTrade(
        "msg-003", "s3", "IL_D91", 1000, 50, 0
      );
      await market.connect(settler).settleTrade(
        "msg-004", "s4", "McHenry_D63", 2000, 40, 0
      );

      expect(await market.districtTradeCount("IL_D91")).to.equal(1);
      expect(await market.districtTradeCount("McHenry_D63")).to.equal(1);
      expect(await market.districtMWhSettled("IL_D91")).to.equal(1000);
      expect(await market.districtMWhSettled("McHenry_D63")).to.equal(2000);
    });
  });

  describe("On-Chain Idempotency", function () {
    it("blocks duplicate message IDs", async function () {
      await market.connect(settler).settleTrade(
        "msg-100", "station-x", "IL_D91", 500, 30, 0
      );

      await expect(
        market.connect(settler).settleTrade(
          "msg-100", "station-x", "IL_D91", 500, 30, 0
        )
      ).to.be.revertedWith("Duplicate message");
    });

    it("increments duplicatesBlocked counter", async function () {
      await market.connect(settler).settleTrade(
        "msg-200", "s1", "IL_D91", 100, 10, 0
      );

      try {
        await market.connect(settler).settleTrade(
          "msg-200", "s1", "IL_D91", 100, 10, 0
        );
      } catch (e) {
        // Expected revert
      }

      expect(await market.duplicatesBlocked()).to.equal(1);
    });

    it("isSettled returns correct status", async function () {
      expect(await market.isSettled("msg-300")).to.equal(false);

      await market.connect(settler).settleTrade(
        "msg-300", "s1", "IL_D91", 100, 10, 0
      );

      expect(await market.isSettled("msg-300")).to.equal(true);
    });

    it("different message IDs settle independently", async function () {
      await market.connect(settler).settleTrade(
        "msg-A", "s1", "IL_D91", 100, 10, 0
      );
      await market.connect(settler).settleTrade(
        "msg-B", "s2", "IL_D91", 200, 20, 0
      );

      expect(await market.tradeCount()).to.equal(2);
    });
  });

  describe("Pause", function () {
    it("owner can pause", async function () {
      await market.setPaused(true);
      await expect(
        market.connect(settler).settleTrade(
          "msg-p1", "s1", "IL_D91", 100, 10, 0
        )
      ).to.be.revertedWith("Contract paused");
    });

    it("owner can unpause", async function () {
      await market.setPaused(true);
      await market.setPaused(false);
      await market.connect(settler).settleTrade(
        "msg-p2", "s1", "IL_D91", 100, 10, 0
      );
      expect(await market.tradeCount()).to.equal(1);
    });

    it("non-owner cannot pause", async function () {
      await expect(
        market.connect(outsider).setPaused(true)
      ).to.be.revertedWith("Only owner");
    });
  });

  describe("TokenL2 Integration", function () {
    it("minter can mint THN", async function () {
      await token.connect(settler).mint(
        settler.address, ethers.parseEther("1.0"), "station-1"
      );
      expect(await token.balanceOf(settler.address)).to.equal(ethers.parseEther("1.0"));
      expect(await token.totalSupply()).to.equal(ethers.parseEther("1.0"));
    });

    it("minter can burn THN", async function () {
      await token.connect(settler).mint(
        settler.address, ethers.parseEther("1.0"), "station-1"
      );
      await token.connect(settler).burn(
        settler.address, ethers.parseEther("0.025"), "grid_toll_IL_D91"
      );
      expect(await token.balanceOf(settler.address)).to.equal(ethers.parseEther("0.975"));
    });

    it("non-minter cannot mint", async function () {
      await expect(
        token.connect(outsider).mint(outsider.address, ethers.parseEther("1.0"), "hack")
      ).to.be.revertedWith("Only minter");
    });

    it("owner can add/remove minters", async function () {
      await token.setMinter(outsider.address, true);
      await token.connect(outsider).mint(outsider.address, ethers.parseEther("1.0"), "s1");
      expect(await token.balanceOf(outsider.address)).to.equal(ethers.parseEther("1.0"));

      await token.setMinter(outsider.address, false);
      await expect(
        token.connect(outsider).mint(outsider.address, ethers.parseEther("1.0"), "s2")
      ).to.be.revertedWith("Only minter");
    });
  });

  describe("Batch Settlement", function () {
    it("settles multiple entries in one tx", async function () {
      const entries = [
        { messageId: "b-001", stationId: "s1", district: "IL_D91", amount: 1000, price: 50, rType: 0, isBridge: false, toDistrict: "" },
        { messageId: "b-002", stationId: "s2", district: "IL_D91", amount: 2000, price: 60, rType: 0, isBridge: false, toDistrict: "" },
        { messageId: "b-003", stationId: "s3", district: "McHenry_D63", amount: 500, price: 40, rType: 0, isBridge: false, toDistrict: "" },
      ];

      const tx = await market.connect(settler).settleBatch(entries);
      const receipt = await tx.wait();

      expect(await market.tradeCount()).to.equal(3);
      expect(await market.districtTradeCount("IL_D91")).to.equal(2);
      expect(await market.districtTradeCount("McHenry_D63")).to.equal(1);
      expect(await market.districtMWhSettled("IL_D91")).to.equal(3000);
    });

    it("returns number of settled entries", async function () {
      const entries = [
        { messageId: "ret-1", stationId: "s1", district: "IL_D91", amount: 100, price: 10, rType: 0, isBridge: false, toDistrict: "" },
        { messageId: "ret-2", stationId: "s2", district: "IL_D91", amount: 200, price: 20, rType: 0, isBridge: false, toDistrict: "" },
      ];

      // Use staticCall to get the return value
      const settled = await market.connect(settler).settleBatch.staticCall(entries);
      expect(settled).to.equal(2);
    });

    it("skips duplicates within batch without reverting", async function () {
      // First, settle one entry normally
      await market.connect(settler).settleTrade(
        "dup-in-batch", "s1", "IL_D91", 100, 10, 0
      );

      // Now batch includes the duplicate
      const entries = [
        { messageId: "dup-in-batch", stationId: "s1", district: "IL_D91", amount: 100, price: 10, rType: 0, isBridge: false, toDistrict: "" },
        { messageId: "new-entry", stationId: "s2", district: "IL_D91", amount: 200, price: 20, rType: 0, isBridge: false, toDistrict: "" },
      ];

      await market.connect(settler).settleBatch(entries);

      // Only 2 total (1 from settleTrade + 1 new from batch, dupe skipped)
      expect(await market.tradeCount()).to.equal(2);
      expect(await market.duplicatesBlocked()).to.equal(1);
    });

    it("handles bridge entries in batch", async function () {
      const entries = [
        { messageId: "br-1", stationId: "s1", district: "IL_D91", amount: 1000, price: 50, rType: 0, isBridge: true, toDistrict: "McHenry_D63" },
        { messageId: "br-2", stationId: "s2", district: "IL_D91", amount: 500, price: 60, rType: 0, isBridge: false, toDistrict: "" },
      ];

      await market.connect(settler).settleBatch(entries);

      const trade1 = await market.trades(1);
      expect(trade1.status).to.equal(2); // Bridged

      const trade2 = await market.trades(2);
      expect(trade2.status).to.equal(1); // Settled
    });

    it("rejects empty batch", async function () {
      await expect(
        market.connect(settler).settleBatch([])
      ).to.be.revertedWith("Empty batch");
    });

    it("non-settler cannot batch settle", async function () {
      const entries = [
        { messageId: "x", stationId: "s1", district: "IL_D91", amount: 100, price: 10, rType: 0, isBridge: false, toDistrict: "" },
      ];
      await expect(
        market.connect(outsider).settleBatch(entries)
      ).to.be.revertedWith("Only settler");
    });
  });

  describe("Fee Withdrawal", function () {
    it("owner can withdraw accumulated fees", async function () {
      // Send some ETH to the contract
      await owner.sendTransaction({
        to: await market.getAddress(),
        value: ethers.parseEther("1.0"),
      });

      const balBefore = await ethers.provider.getBalance(owner.address);
      const tx = await market.withdrawFees();
      const receipt = await tx.wait();
      const gasCost = receipt.gasUsed * receipt.gasPrice;
      const balAfter = await ethers.provider.getBalance(owner.address);

      expect(balAfter + gasCost - balBefore).to.be.closeTo(
        ethers.parseEther("1.0"), ethers.parseEther("0.001")
      );
    });
  });
});
